import os
import json
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import boto3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret")

# =========================
# DATABASE
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# =========================
# S3
# =========================
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=os.environ["AWS_REGION"]
)
BUCKET = os.environ["S3_BUCKET"]

# =========================
# MODEL
# =========================
class Cotizacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.Integer, unique=True, nullable=False)

    nombre_cliente = db.Column(db.String(150))
    contacto = db.Column(db.String(150))
    email = db.Column(db.String(120))
    telefono = db.Column(db.String(40))

    fecha_contrato = db.Column(db.Date, default=datetime.utcnow)
    dias_entrega = db.Column(db.Integer, default=15)
    vigencia = db.Column(db.Integer, default=15)

    titulo_proyecto = db.Column(db.String(200))
    descripcion = db.Column(db.Text)
    instalado = db.Column(db.String(50))
    diseno = db.Column(db.String(50))

    items = db.Column(db.Text)
    subtotal = db.Column(db.Float)
    total = db.Column(db.Float)

    s3_key = db.Column(db.String(400))

with app.app_context():
    db.create_all()

# =========================
# PDF
# =========================
def generar_pdf(cot, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 820

    def w(txt):
        nonlocal y
        c.drawString(40, y, str(txt))
        y -= 16

    w(f"COTIZACIÓN #{cot.numero
