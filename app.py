from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import date
import boto3
import os
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

S3_BUCKET = "cotizaciones-pdfs"

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    region_name=os.environ.get("AWS_REGION"),
)

# ===================== MODELOS =====================

class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.String, unique=True)
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

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizacion.id"))
    cantidad = db.Column(db.Float)
    detalle = db.Column(db.String)
    precio = db.Column(db.Float)
    monto = db.Column(db.Float)

# ===================== HELPERS =====================

def generar_numero():
    hoy = date.today().strftime("%Y-%m-%d")
    ultimo = Cotizacion.query.filter(
        Cotizacion.numero_registro.like(f"{hoy}-%")
    ).order_by(Cotizacion.numero_registro.desc()).first()

    sec = 1 if not ultimo else int(ultimo.numero_registro.split("-")[-1]) + 1
    return f"{hoy}-{sec:04d}"

def generar_pdf(cot, items, path):
    c = canvas.Canvas(path, pagesize=LETTER)
    y = 750

    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, y, "ROTULOS FREER S.A.")
    c.drawRightString(580, y, f"N° {cot.numero_registro}")

    y -= 40
    c.setFont("Helvetica", 10)
    c.drawString(30, y, f"Cliente: {cot.nombre_cliente}")
    y -= 15
    c.drawString(30, y, f"Contacto: {cot.contacto}")
    y -= 15
    c.drawString(30, y, f"Email: {cot.email}")
    y -= 15
    c.drawString(30, y, f"Tel: {cot.telefono}")

    y -= 30
    c.drawString(30, y, "Cantidad")
    c.drawString(90, y, "Detalle")
    c.drawString(400, y, "P.Unit")
    c.drawString(480, y, "Monto")

    y -= 15
    for i in items:
        c.drawString(30, y, str(i.cantidad))
        c.drawString(90, y, i.detalle)
        c.drawRightString(450, y, f"{i.precio:.2f}")
        c.drawRightString(580, y, f"{i.monto:.2f}")
        y -= 15

    y -= 20
    c.drawRightString(450, y, "Subtotal")
    c.drawRightString(580, y, f"{cot.subtotal:.2f}")
    y -= 15
    c.drawRightString(450, y, "Total")
    c.drawRightString(580, y, f"{cot.total:.2f}")

    c.save()

# ===================== ROUTE =====================

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        numero = generar_numero()

        cot = Cotizacion(
            numero_registro=numero,
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
            subtotal=0,
            total=0,
        )
        db.session.add(cot)
        db.session.commit()

        cantidades = request.form.getlist("cantidad[]")
        detalles = request.form.getlist("detalle[]")
        precios = request.form.getlist("precio[]")

        subtotal = 0
        items = []

        for c, d, p in zip(cantidades, detalles, precios):
            monto = float(c) * float(p)
            subtotal += monto
            item = Item(
                cotizacion_id=cot.id,
                cantidad=float(c),
                detalle=d,
                precio=float(p),
                monto=monto,
            )
            db.session.add(item)
            items.append(item)

        cot.subtotal = subtotal
        cot.total = subtotal * 1.13
        db.session.commit()

        os.makedirs("/tmp/pdfs", exist_ok=True)
        pdf_path = f"/tmp/pdfs/{numero}.pdf"
        generar_pdf(cot, items, pdf_path)

        s3_key = f"{cot.nombre_cliente}/{numero}/cotizacion.pdf"
        s3.upload_file(pdf_path, S3_BUCKET, s3_key)

        cot.s3_key = s3_key
        db.session.commit()

        return redirect("/")

    return render_template("index.html")

with app.app_context():
    db.create_all()
