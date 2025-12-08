import os
from flask import Flask, render_template, request, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from io import BytesIO
import boto3
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

# ------------------------
# CONFIGURACIÓN FLASK
# ------------------------
app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------------
# AWS / S3
# ------------------------
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    region_name=os.environ.get("AWS_REGION"),
)

S3_BUCKET = os.environ.get("S3_BUCKET")

# ------------------------
# MODELO BD
# ------------------------
class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contrato = db.Column(db.String(100))
    cliente = db.Column(db.String(200))
    telefono = db.Column(db.String(50))
    descripcion = db.Column(db.Text)
    subtotal = db.Column(db.Float)
    iva = db.Column(db.Float)
    total = db.Column(db.Float)
    fecha = db.Column(db.String(20))
    s3_key = db.Column(db.String(300))

# ✅ CREAR TABLAS AUTOMÁTICAMENTE (PRODUCCIÓN)
with app.app_context():
    db.create_all()

# ------------------------
# RUTAS
# ------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        contrato = request.form["contrato"]
        cliente = request.form["cliente"]
        telefono = request.form["telefono"]
        descripcion = request.form["descripcion"]
        subtotal = float(request.form["subtotal"])

        iva = subtotal * 0.13
        total = subtotal + iva
        fecha = datetime.now().strftime("%d/%m/%Y")

        # ------------------------
        # CREAR PDF EN MEMORIA
        # ------------------------
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=LETTER)
        c.setFont("Helvetica", 10)

        c.drawString(50, 750, "COTIZACIÓN")
        c.drawString(50, 730, f"Contrato: {contrato}")
        c.drawString(50, 715, f"Cliente: {cliente}")
        c.drawString(50, 700, f"Teléfono: {telefono}")
        c.drawString(50, 680, f"Fecha: {fecha}")

        c.drawString(50, 640, "Descripción:")
        c.drawString(50, 620, descripcion)

        c.drawString(50, 560, f"Subtotal: ₡ {subtotal:,.2f}")
        c.drawString(50, 540, f"IVA (13%): ₡ {iva:,.2f}")
        c.drawString(50, 520, f"Total: ₡ {total:,.2f}")

        c.showPage()
        c.save()

        buffer.seek(0)

        # ------------------------
        # SUBIR PDF A S3
        # ------------------------
        cliente_folder = cliente.replace(" ", "_").lower()
        filename = f"cotizacion_{contrato}_{fecha}.pdf"
        s3_key = f"{cliente_folder}/{filename}"

        s3.upload_fileobj(
            buffer,
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )

        # ------------------------
        # GUARDAR BD
        # ------------------------
        cot = Cotizacion(
            contrato=contrato,
            cliente=cliente,
            telefono=telefono,
            descripcion=descripcion,
            subtotal=subtotal,
            iva=iva,
            total=total,
            fecha=fecha,
            s3_key=s3_key,
        )
        db.session.add(cot)
        db.session.commit()

        return render_template(
            "exito.html",
            cliente=cliente,
            contrato=contrato,
            s3_key=s3_key
        )

    return render_template("formulario.html")


@app.route("/descargar")
def descargar_pdf():
    s3_key = request.args.get("key")

    buffer = BytesIO()
    s3.download_fileobj(S3_BUCKET, s3_key, buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=s3_key.split("/")[-1],
        mimetype="application/pdf",
    )

# ------------------------
# ENTRYPOINT
# ------------------------
if __name__ == "__main__":
    app.run(debug=True)
