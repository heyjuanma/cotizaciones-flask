from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime, timedelta
import boto3
import os
import io
import urllib.parse

app = Flask(__name__)

# Configuración desde env
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Modelo
class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contrato = db.Column(db.String(50))
    cliente = db.Column(db.String(200))
    telefono = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    subtotal = db.Column(db.Float)
    iva = db.Column(db.Float)
    total = db.Column(db.Float)
    fecha = db.Column(db.String(50))
    s3_key = db.Column(db.String(500))  # ruta en S3

# Cliente S3 (usa variables de entorno)
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    region_name=os.environ.get("AWS_REGION")
)

S3_BUCKET = os.environ.get("S3_BUCKET")

# función para nombres seguros de carpeta/archivo
def nombre_seguro(nombre):
    limpio = ""
    for c in nombre:
        if c.isalnum() or c in (" ", "_", "-"):
            limpio += c
    return limpio.strip().replace(" ", "_").upper()

# generar PDF en memoria (bytes)
def generar_pdf_bytes(cot):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica", 10)

    c.drawString(50, 740, "ROTULOS FREER S.A.")
    c.drawString(50, 725, "COTIZACIÓN / CONTRATO")
    c.drawString(400, 740, f"N° {cot.contrato}")
    c.drawString(400, 725, f"Fecha: {cot.fecha}")

    c.line(50, 715, 550, 715)

    c.drawString(50, 690, f"Cliente: {cot.cliente}")
    c.drawString(50, 675, f"Teléfono: {cot.telefono}")

    c.drawString(50, 640, "Descripción:")
    text = c.beginText(50, 625)
    for line in cot.descripcion.split("\n"):
        text.textLine(line)
    c.drawText(text)

    c.line(50, 300, 550, 300)

    c.drawString(350, 275, f"Subtotal: ₡{cot.subtotal:,.2f}")
    c.drawString(350, 260, f"IVA 13%: ₡{cot.iva:,.2f}")
    c.drawString(350, 245, f"TOTAL: ₡{cot.total:,.2f}")

    c.drawString(50, 200, "Forma de pago: 50% prima / saldo contra entrega")
    c.drawString(50, 180, "Pagadero en colones según tipo de cambio BCCR")

    c.drawString(50, 120, "Firma autorizada __________________________")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# generar URL prefirmada para descarga (temporal)
def generar_presigned_url(s3_key, expires_in=3600):
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in
        )
        return url
    except Exception as e:
        app.logger.error("Error generando presigned URL: %s", e)
        return None

# RUTA PRINCIPAL: mostrar formulario y procesar
@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = None
    download_url = None

    if request.method == "POST":
        cliente = request.form.get("cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        try:
            subtotal = float(request.form.get("subtotal", "0") or 0)
        except:
            subtotal = 0.0

        iva = round(subtotal * 0.13, 2)
        total = round(subtotal + iva, 2)
        fecha = datetime.now().strftime("%d/%m/%Y")

        # guardar en DB
        cot = Cotizacion(
            cliente=cliente,
            telefono=telefono,
            descripcion=descripcion,
            subtotal=subtotal,
            iva=iva,
            total=total,
            fecha=fecha
        )
        db.session.add(cot)
        db.session.commit()

        cot.contrato = f"{datetime.now().year}-{cot.id:05d}"
        # crear nombre seguro y key S3
        cliente_folder = nombre_seguro(cliente or "CLIENTE_SIN_NOMBRE")
        s3_key = f"{urllib.parse.quote(cliente_folder)}/{urllib.parse.quote(cot.contrato)}.pdf"
        cot.s3_key = s3_key

        db.session.commit()

        # generar pdf bytes y subir a s3
        pdf_bytes = generar_pdf_bytes(cot)

        try:
            s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=pdf_bytes, ContentType="application/pdf")
        except Exception as e:
            app.logger.error("Error subiendo a S3: %s", e)
            mensaje = "Error subiendo el PDF a S3. Revisa credenciales y bucket."
            return render_template("formulario.html", mensaje=mensaje)

        # generar URL de descarga temporal
        download_url = generar_presigned_url(s3_key, expires_in=3600)
        mensaje = "Cotización creada y guardada en la nube ✅"

        return render_template("formulario.html", mensaje=mensaje, download_url=download_url, contrato=cot.contrato, cliente=cliente)

    return render_template("formulario.html")

if __name__ == "__main__":
    app.run()

