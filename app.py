import os
import io
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy

import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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
    contacto = db.Column(db.String)  # <- queda igual, no se usa
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


def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 800

    def w(texto):
        nonlocal y
        c.drawString(40, y, str(texto))
        y -= 16

    w(f"COTIZACIÓN #{cot.numero_registro}")
    w(f"Fecha contrato: {cot.fecha_contrato}")
    w("")
    w(f"Cliente: {cot.nombre_cliente}")
    w(f"Email: {cot.email}")
    w(f"Teléfono: {cot.telefono}")
    w("")
    w(f"Días de entrega: {cot.dias_entrega}")
    w(f"Vigencia: {cot.vigencia} días")
    w("")
    w(f"Proyecto: {cot.titulo_proyecto}")
    w(cot.descripcion)
    w("")
    w("Detalle:")

    for i in items:
        w(f"{i['cantidad']} | {i['detalle']} | {i['precio']} | {i['monto']}")

    w("")
    w(f"Subtotal: {cot.subtotal}")
    w(f"Total (IVA 13%): {cot.total}")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":

        hoy = datetime.today().date()
        fecha_str = hoy.strftime("%Y-%m-%d")

        ultimo = (
            Cotizacion.query
            .filter(Cotizacion.numero_registro.like(f"{fecha_str}-%"))
            .order_by(Cotizacion.numero_registro.desc())
            .first()
        )

        if ultimo:
            ultimo_num = int(ultimo.numero_registro.split("-")[-1])
            consecutivo = ultimo_num + 1
        else:
            consecutivo = 1

        numero = f"{fecha_str}-{consecutivo:04d}"

        items = json.loads(request.form["items"])
        subtotal = sum(i["monto"] for i in items)
        total = round(subtotal * 1.13, 2)

        cot = Cotizacion(
            numero_registro=numero,
            nombre_cliente=request.form.get("nombre_cliente"),
            email=request.form.get("email"),
            telefono=request.form.get("telefono"),

            dias_entrega=15,
            fecha_contrato=hoy,
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

        folder = f"{cot.nombre_cliente}/{cot.numero_registro}/cotizacion.pdf"

        s3.upload_fileobj(
            pdf,
            S3_BUCKET,
            folder,
            ExtraArgs={"ContentType": "application/pdf"}
        )

        cot.s3_key = folder
        db.session.commit()

        return redirect(url_for("index"))

    cotizaciones = Cotizacion.query.order_by(Cotizacion.numero_registro.asc()).all()
    return render_template("index.html", cotizaciones=cotizaciones)


@app.route("/download/<int:id>")
def download(id):
    cot = Cotizacion.query.get_or_404(id)
    obj = s3.get_object(Bucket=S3_BUCKET, Key=cot.s3_key)
    return send_file(
        io.BytesIO(obj["Body"].read()),
        as_attachment=True,
        download_name="cotizacion.pdf"
    )


@app.route("/reset-db")
def reset_db():
    db.drop_all()
    db.create_all()
    return "Base de datos reiniciada ✅"


with app.app_context():
    db.create_all()
