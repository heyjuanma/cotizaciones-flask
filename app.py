from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import date
import boto3
import os
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

# ================= CONFIG =================

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

# ================= MODELS =================

class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.String, unique=True, nullable=False)

    nombre_cliente = db.Column(db.String)
    contacto = db.Column(db.String)
    email = db.Column(db.String)
    telefono = db.Column(db.String)

    dias_entrega = db.Column(db.Integer, default=15)
    fecha_contrato = db.Column(db.Date)
    vigencia = db.Column(db.Integer, default=15)

    titulo_proyecto = db.Column(db.String)
    descripcion = db.Column(db.Text)
    instalado = db.Column(db.String)
    diseno = db.Column(db.String)

    subtotal = db.Column(db.Float)
    total = db.Column(db.Float)

    s3_key = db.Column(db.String)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizaciones.id"))
    cantidad = db.Column(db.Float)
    detalle = db.Column(db.String)
    precio_unitario = db.Column(db.Float)
    monto = db.Column(db.Float)

# ================= UTILS =================

def generar_numero_contrato():
    hoy = date.today().strftime("%Y-%m-%d")

    ultimo = (
        Cotizacion.query
        .filter(Cotizacion.numero_registro.like(f"{hoy}-%"))
        .order_by(Cotizacion.numero_registro.desc())
        .first()
    )

    secuencia = 1 if not ultimo else int(ultimo.numero_registro.split("-")[-1]) + 1
    return f"{hoy}-{secuencia:04d}"

def generar_pdf(cot, items, filepath):
    c = canvas.Canvas(filepath, pagesize=LETTER)
    y = 750

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "ROTULOS FREER S.A.")
    c.setFillColorRGB(1, 0, 0)
    c.drawRightString(570, y, f"N° {cot.numero_registro}")
    c.setFillColorRGB(0, 0, 0)

    y -= 40
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Cliente: {cot.nombre_cliente}")
    y -= 15
    c.drawString(40, y, f"Contacto: {cot.contacto}")
    y -= 15
    c.drawString(40, y, f"Email: {cot.email}")
    y -= 15
    c.drawString(40, y, f"Teléfono: {cot.telefono}")

    y -= 20
    c.drawString(40, y, f"Fecha contrato: {cot.fecha_contrato}")
    c.drawString(300, y, f"Días entrega: {cot.dias_entrega}")
    y -= 15
    c.drawString(40, y, f"Vigencia: {cot.vigencia} días")

    y -= 25
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Detalle")
    y -= 15
    c.setFont("Helvetica", 10)
    c.drawString(40, y, cot.descripcion)

    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Cantidad")
    c.drawString(100, y, "Detalle")
    c.drawString(360, y, "P.Unit")
    c.drawString(460, y, "Monto")

    y -= 15
    c.setFont("Helvetica", 10)
    for i in items:
        c.drawString(40, y, str(i.cantidad))
        c.drawString(100, y, i.detalle)
        c.drawRightString(440, y, f"{i.precio_unitario:.2f}")
        c.drawRightString(540, y, f"{i.monto:.2f}")
        y -= 15

    y -= 20
    c.drawRightString(440, y, "Subtotal:")
    c.drawRightString(540, y, f"{cot.subtotal:.2f}")
    y -= 15
    c.drawRightString(440, y, "Total:")
    c.drawRightString(540, y, f"{cot.total:.2f}")

    c.save()

# ================= ROUTES =================

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":

        numero = generar_numero_contrato()

        cot = Cotizacion(
            numero_registro=numero,
            nombre_cliente=request.form["nombre_cliente"],
            contacto=request.form["contacto"],
            email=request.form["email"],
            telefono=request.form["telefono"],
            dias_entrega=15,
            fecha_contrato=date.today(),
            vigencia=15,
            titulo_proyecto=request.form["titulo_proyecto"],
            descripcion=request.form["descripcion"],
            instalado=request.form["instalado"],
            diseno=request.form["diseno"],
            subtotal=0,
            total=0
        )

        db.session.add(cot)
        db.session.commit()

        items = []
        subtotal = 0

        for i in range(len(request.form.getlist("cantidad"))):
            cantidad = float(request.form.getlist("cantidad")[i])
            precio = float(request.form.getlist("precio")[i])
            monto = cantidad * precio
            subtotal += monto

            item = Item(
                cotizacion_id=cot.id,
                cantidad=cantidad,
                detalle=request.form.getlist("detalle")[i],
                precio_unitario=precio,
                monto=monto
            )
            items.append(item)
            db.session.add(item)

        cot.subtotal = subtotal
        cot.total = subtotal * 1.13

        db.session.commit()

        os.makedirs("/tmp/pdf", exist_ok=True)
        pdf_path = f"/tmp/pdf/{numero}.pdf"
        generar_pdf(cot, items, pdf_path)

        s3_key = f"{cot.nombre_cliente}/{numero}/cotizacion.pdf"
        s3.upload_file(pdf_path, S3_BUCKET, s3_key)
        cot.s3_key = s3_key
        db.session.commit()

        return redirect(url_for("index"))

    return render_template("index.html")

# ================= INIT =================

with app.app_context():
    db.create_all()

