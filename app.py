import os
import io
import json
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy

import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, black

# --------------------
# CONFIGURACIÓN FLASK
# --------------------
app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///local.db"
).replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# --------------------
# CONFIGURACIÓN S3
# --------------------
S3_BUCKET = "cotizaciones-pdfs"

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)

# --------------------
# MODELO
# --------------------
class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.String, unique=True, nullable=False)

    nombre_cliente = db.Column(db.String)
    contacto = db.Column(db.String)
    email = db.Column(db.String)
    telefono = db.Column(db.String)

    dias_entrega = db.Column(db.Integer)
    fecha_contrato = db.Column(db.Date)
    vigencia = db.Column(db.Integer)

    titulo_proyecto = db.Column(db.String)
    descripcion = db.Column(db.Text)
    instalado = db.Column(db.String)
    diseno = db.Column(db.String)

    subtotal = db.Column(db.Float)
    total = db.Column(db.Float)

    s3_key = db.Column(db.String)

# --------------------
# GENERAR NUMERO CONTRATO
# --------------------
def generar_numero_contrato():
    hoy = date.today().strftime("%Y-%m-%d")
    ultimo = (
        Cotizacion.query
        .filter(Cotizacion.numero_registro.startswith(hoy))
        .order_by(Cotizacion.numero_registro.desc())
        .first()
    )

    secuencia = 1
    if ultimo:
        secuencia = int(ultimo.numero_registro.split("-")[-1]) + 1

    return f"{hoy}-{secuencia:04d}"

# --------------------
# PDF FORMATEADO
# --------------------
def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40

    # CONTRATO
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(red)
    c.drawRightString(width - 40, y, f"Contrato Nº {cot.numero_registro}")
    c.setFillColor(black)

    y -= 35
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Nombre del Cliente: {cot.nombre_cliente}")

    y -= 15
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Contacto: {cot.contacto}")

    y -= 15
    c.drawString(40, y, f"Email: {cot.email}")
    c.drawString(300, y, f"Fecha contrato: {cot.fecha_contrato}")

    y -= 15
    c.drawString(40, y, f"Teléfono: {cot.telefono}")
    c.drawString(300, y, "Días entrega: 15 Días")

    y -= 15
    c.drawString(300, y, "Vigencia contrato: 15 Días")

    y -= 35
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, cot.titulo_proyecto)

    y -= 25

    # TABLA HEADER
    c.setFont("Helvetica-Bold", 9)
    c.rect(40, y, 520, 20)
    c.drawString(45, y + 6, "Cantidad")
    c.drawString(110, y + 6, "Detalle")
    c.drawString(350, y + 6, "Precio unit.")
    c.drawString(430, y + 6, "Monto")
    c.drawString(495, y + 6, "Imp")

    y -= 20
    c.setFont("Helvetica", 9)

    for item in items:
        c.rect(40, y, 520, 20)
        c.drawString(50, y + 6, str(item["cantidad"]))
        c.drawString(110, y + 6, item["detalle"])
        c.drawRightString(420, y + 6, f'{item["precio"]:.2f}')
        c.drawRightString(480, y + 6, f'{item["monto"]:.2f}')
        c.drawString(500, y + 6, "E")
        y -= 20

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(420, y, "Subtotal:")
    c.drawRightString(480, y, f"{cot.subtotal:.2f}")

    y -= 15
    c.drawRightString(420, y, "Impuesto 13%:")
    c.drawRightString(480, y, f"{(cot.total - cot.subtotal):.2f}")

    y -= 15
    c.drawRightString(420, y, "Total:")
    c.drawRightString(480, y, f"{cot.total:.2f}")

    y -= 50
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "Firma autorizada")
    y -= 15
    c.drawString(40, y, "Juan Freer Bustamante")
    y -= 15
    c.drawString(40, y, "Gerente General")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --------------------
# RUTAS
# --------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        items = json.loads(request.form["items"])
        subtotal = sum(i["monto"] for i in items)
        total = round(subtotal * 1.13, 2)

        cot = Cotizacion(
            numero_registro=generar_numero_contrato(),
            nombre_cliente=request.form.get("nombre_cliente"),
            contacto=request.form.get("contacto"),
            email=request.form.get("email"),
            telefono=request.form.get("telefono"),
            dias_entrega=15,
            fecha_contrato=date.today(),
            vigencia=15,
            titulo_proyecto=request.form.get("titulo_proyecto"),
            descripcion=request.form.get("descripcion"),
            instalado=request.form.get("instalado"),
            diseno=request.form.get("diseno"),
            subtotal=subtotal,
            total=total
        )

        db.session.add(cot)
        db.session.commit()

        pdf = generar_pdf(cot, items)
        key = f"{cot.nombre_cliente}/{cot.numero_registro}/cotizacion.pdf"

        s3.upload_fileobj(pdf, S3_BUCKET, key, ExtraArgs={"ContentType": "application/pdf"})
        cot.s3_key = key
        db.session.commit()

        return redirect(url_for("index"))

    cotizaciones = Cotizacion.query.order_by(Cotizacion.numero_registro.desc()).all()
    return render_template("index.html", cotizaciones=cotizaciones)

@app.route("/download/<int:id>")
def download(id):
    cot = Cotizacion.query.get_or_404(id)
    obj = s3.get_object(Bucket=S3_BUCKET, Key=cot.s3_key)
    return send_file(io.BytesIO(obj["Body"].read()), as_attachment=True, download_name="cotizacion.pdf")

with app.app_context():
    db.create_all()
