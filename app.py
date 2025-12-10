import os
import io
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy

import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///local.db"
).replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


S3_BUCKET = "cotizaciones-pdfs"

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)


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


def draw_multiline(c, text, x, y, max_width):
    textobject = c.beginText(x, y)
    textobject.setFont("Helvetica", 10)

    for line in text.split("\n"):
        words = line.split(" ")
        current = ""
        for w in words:
            if c.stringWidth(current + w, "Helvetica", 10) < max_width:
                current += w + " "
            else:
                textobject.textLine(current)
                current = w + " "
        textobject.textLine(current)

    c.drawText(textobject)
    return textobject.getY()


def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    # LOGO
    logo_path = os.path.join(app.root_path, "static", "logo.png")
    if os.path.exists(logo_path):
        c.drawImage(ImageReader(logo_path), 40, y - 40, width=120, preserveAspectRatio=True)

    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(1, 0, 0)
    c.drawRightString(width - 40, y, f"Contrato #{cot.numero_registro}")

    y -= 60
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Nombre del Cliente: {cot.nombre_cliente}")

    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Contacto: {cot.contacto}")
    y -= 15
    c.drawString(40, y, f"Email: {cot.email}")
    y -= 15
    c.drawString(40, y, f"Teléfono: {cot.telefono}")

    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, cot.titulo_proyecto)

    # CUADRO DE TEXTO PARA DESCRIPCIÓN
    y -= 20
    box_height = 100  # Ajusta según el tamaño que necesites
    c.rect(40, y - box_height, width - 80, box_height)  # Dibuja el cuadro
    y_text_start = y - 15
    y_text_end = draw_multiline(c, cot.descripcion, 45, y_text_start, width - 100)
    y = y_text_end - 20  # Ajusta posición para la tabla

    # TABLA COMPLETA CON BORDES
    col_x = [40, 100, 350, 450, 540]
    row_h = 20

    headers = ["Cant", "Detalle", "Precio", "Monto"]
    c.setFont("Helvetica-Bold", 10)
    for i, h in enumerate(headers):
        c.drawString(col_x[i] + 5, y, h)

    y -= row_h
    c.setFont("Helvetica", 9)

    # Filas de la tabla
    row_positions = []
    for item in items:
        y_start = y
        y_end = draw_multiline(c, str(item["detalle"]), col_x[1] + 5, y, col_x[2] - col_x[1] - 10)
        max_y = min(y_end, y_start - row_h)

        c.drawString(col_x[0] + 5, y_start, str(item["cantidad"]))
        c.drawString(col_x[2] + 5, y_start, f"{item['precio']}")
        c.drawString(col_x[3] + 5, y_start, f"{item['monto']}")

        row_positions.append((y_start, max_y))
        y = max_y - 5

    # DIBUJAR TODOS LOS BORDES DE LA TABLA
    top = row_positions[0][0] + 5
    bottom = row_positions[-1][1] - 5
    for x in col_x:
        c.line(x, top, x, bottom)
    c.line(col_x[-1], top, col_x[-1], bottom)

    for y_top, y_bottom in row_positions:
        c.line(col_x[0], y_top, col_x[-1], y_top)
    c.line(col_x[0], bottom, col_x[-1], bottom)

    # Nota y total
    y -= 30
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Pagadera en colones al tipo de cambio de la fecha de cancelación de la factura")
    y -= 12
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Forma de Pago: 50% de prima, cancelación contra entrega")

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 40, y + 12, f"Subtotal: ₡{cot.subtotal}")
    c.drawRightString(width - 40, y - 5, f"Total (13%): ₡{cot.total}")

    y -= 50
    c.drawString(40, y, "Firma autorizada")
    y -= 12
    c.drawString(40, y, "Juan Freer Bustamante")
    y -= 12
    c.drawString(40, y, "Gerente General")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        fecha = datetime.now().strftime("%Y-%m-%d")
        count = Cotizacion.query.filter(Cotizacion.numero_registro.like(f"{fecha}%")).count() + 1
        numero = f"{fecha}-{count:04d}"

        items = json.loads(request.form["items"])
        subtotal = sum(i["monto"] for i in items)
        total = round(subtotal * 1.13, 2)

        cot = Cotizacion(
            numero_registro=numero,
            nombre_cliente=request.form["nombre_cliente"],
            contacto=request.form["contacto"],
            email=request.form["email"],
            telefono=request.form["telefono"],
            dias_entrega=15,
            fecha_contrato=datetime.today().date(),
            vigencia=15,
            titulo_proyecto=request.form["titulo_proyecto"],
            descripcion=request.form["descripcion"],
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
