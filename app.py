import os
import io
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import boto3

app = Flask(__name__)

# ---------------- CONFIG ----------------
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret")

db = SQLAlchemy(app)

S3_BUCKET = os.environ.get("S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION")

s3 = boto3.client("s3", region_name=AWS_REGION)

# ---------------- MODELO ----------------
class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.Integer, unique=True)
    nombre_cliente = db.Column(db.String(120))
    contacto = db.Column(db.String(120))
    email = db.Column(db.String(120))
    telefono = db.Column(db.String(50))
    dias_entrega = db.Column(db.Integer)
    fecha_contrato = db.Column(db.Date)
    vigencia = db.Column(db.Integer)
    titulo_proyecto = db.Column(db.String(200))
    descripcion = db.Column(db.Text)
    instalado = db.Column(db.String(10))
    diseno = db.Column(db.String(10))
    subtotal = db.Column(db.Float)
    total = db.Column(db.Float)
    s3_key = db.Column(db.String(300))

# ---------------- PDF ----------------
def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 820

    def w(text):
        nonlocal y
        c.drawString(40, y, str(text))
        y -= 16

    w(f"COTIZACIÓN #{cot.numero_registro}")
    w(f"Fecha: {cot.fecha_contrato}")
    w("")
    w(f"Cliente: {cot.nombre_cliente}")
    w(f"Contacto: {cot.contacto}")
    w(f"Email: {cot.email}")
    w(f"Teléfono: {cot.telefono}")
    w("")
    w(f"Días entrega: {cot.dias_entrega}")
    w(f"Vigencia: {cot.vigencia} días")
    w("")
    w(f"Proyecto: {cot.titulo_proyecto}")
    w(cot.descripcion)
    w("")
    w("DETALLE:")

    for i in items:
        w(f"{i['cantidad']} x {i['detalle']} @ {i['precio']} = {i['monto']}")

    w("")
    w(f"Subtotal: {cot.subtotal}")
    w(f"Total + 13%: {cot.total}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ---------------- RUTAS ----------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        items = json.loads(request.form["items"])
        subtotal = sum(float(i["monto"]) for i in items)
        total = round(subtotal * 1.13, 2)

        ultimo = db.session.query(db.func.max(Cotizacion.numero_registro)).scalar()
        numero = (ultimo or 0) + 1

        cot = Cotizacion(
            numero_registro=numero,
            nombre_cliente=request.form["nombre_cliente"],
            contacto=request.form["contacto"],
            email=request.form["email"],
            telefono=request.form["telefono"],
            dias_entrega=15,
            fecha_contrato=datetime.utcnow().date(),
            vigencia=15,
            titulo_proyecto=request.form["titulo_proyecto"],
            descripcion=request.form["descripcion"],
            instalado=request.form["instalado"],
            diseno=request.form["diseno"],
            subtotal=subtotal,
            total=total,
        )

        pdf = generar_pdf(cot, items)

        cliente_folder = cot.nombre_cliente.replace(" ", "_")
        s3_key = f"{cliente_folder}/Contrato_{numero}/cotizacion_{numero}.pdf"

        s3.upload_fileobj(pdf, S3_BUCKET, s3_key)

        cot.s3_key = s3_key

        db.session.add(cot)
        db.session.commit()

        return redirect("/")

    cotizaciones = Cotizacion.query.order_by(Cotizacion.numero_registro.desc()).all()
    return render_template("index.html", cotizaciones=cotizaciones)

@app.route("/descargar/<int:id>")
def descargar(id):
    cot = Cotizacion.query.get_or_404(id)
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": cot.s3_key},
        ExpiresIn=60
    )
    return redirect(url)

# ---------------- INIT ----------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
