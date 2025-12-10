import os
import io
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy

import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, black
from reportlab.lib.units import cm


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
# MODELOS
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

    subtotal = db.Column(db.Float)
    total = db.Column(db.Float)

    s3_key = db.Column(db.String)


# --------------------
# PDF
# --------------------
def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # LOGO
    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 40, height - 100, width=120, preserveAspectRatio=True)

    # NUMERO CONTRATO
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(red)
    c.drawRightString(width - 40, height - 60, f"Contrato Nº {cot.numero_registro}")
    c.setFillColor(black)

    y = height - 130

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Nombre del Cliente: {cot.nombre_cliente}")
    y -= 18
    c.drawString(40, y, f"Contacto: {cot.contacto}")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Email: {cot.email}")
    c.drawString(300, y, f"Fecha de contrato: {cot.fecha_contrato}")
    y -= 18
    c.drawString(40, y, f"Teléfono: {cot.telefono}")
    c.drawString(300, y, "Días de entrega: 15 días")
    y -= 18
    c.drawString(300, y, "Vigencia del contrato: 15 días")

    # TITULO
    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, cot.titulo_proyecto.upper())

    # CUADRO DESCRIPCIÓN
    y -= 30
    c.rect(40, y - 60, width - 80, 60)
    text = c.beginText(50, y - 20)
    text.setFont("Helvetica", 10)
    text.textLine(cot.descripcion)
    c.drawText(text)

    # TABLA
    y -= 100
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Cant.")
    c.drawString(90, y, "Detalle")
    c.drawString(320, y, "Precio")
    c.drawString(400, y, "Monto")

    c.line(40, y - 2, width - 40, y - 2)

    y -= 20
    c.setFont("Helvetica", 10)

    for i in items:
        c.drawString(40, y, str(i["cantidad"]))
        c.drawString(90, y, i["detalle"])
        c.drawRightString(370, y, f"{i['precio']:.2f}")
        c.drawRightString(460, y, f"{i['monto']:.2f}")
        c.line(40, y - 5, width - 40, y - 5)
        y -= 18

    # NOTAS
    y -= 20
    c.setFont("Helvetica", 8)
    c.drawString(40, y, "Pagadera en colones al tipo de cambio de la fecha de cancelación de la factura")
    y -= 12
    c.drawString(40, y, "según el tipo de cambio para la venta del Banco Central de Costa Rica.")
    y -= 14
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Forma de Pago: 50% de prima, cancelación contra entrega.")

    # TOTALES
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 40, y + 20, f"Subtotal: {cot.subtotal:.2f}")
    c.drawRightString(width - 40, y, f"Total (IVA 13%): {cot.total:.2f}")

    # FIRMA
    y -= 60
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "Firma autorizada")
    y -= 30
    c.drawString(40, y, "Juan Freer Bustamante")
    y -= 14
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

        today = datetime.now().strftime("%Y-%m-%d")

        last = Cotizacion.query.filter(
            Cotizacion.numero_registro.like(f"{today}%")
        ).order_by(Cotizacion.numero_registro.desc()).first()

        seq = int(last.numero_registro[-4:]) + 1 if last else 1
        numero = f"{today}-{seq:04d}"

        items = json.loads(request.form["items"])
        subtotal = sum(i["monto"] for i in items)
        total = round(subtotal * 1.13, 2)

        cot = Cotizacion(
            numero_registro=numero,
            nombre_cliente=request.form.get("nombre_cliente"),
            contacto=request.form.get("contacto"),
            email=request.form.get("email"),
            telefono=request.form.get("telefono"),
            dias_entrega=15,
            fecha_contrato=datetime.today().date(),
            vigencia=15,
            titulo_proyecto=request.form.get("titulo_proyecto"),
            descripcion=request.form.get("descripcion"),
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
    return send_file(io.BytesIO(obj["Body"].read()),
                     as_attachment=True,
                     download_name="cotizacion.pdf")


with app.app_context():
    db.create_all()
