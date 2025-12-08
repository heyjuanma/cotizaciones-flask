from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from datetime import datetime
import io
import boto3
import psycopg2
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Image

app = Flask(__name__)
app.secret_key = "tu_clave_secreta"

# Configuración S3
S3_BUCKET = "tu-bucket"
S3_REGION = "tu-region"
s3_client = boto3.client("s3")

# Configuración PostgreSQL
conn = psycopg2.connect(
    host="tu_host",
    database="tu_db",
    user="tu_user",
    password="tu_password"
)

@app.route("/", methods=["GET", "POST"])
def formulario():
    if request.method == "POST":
        # Campos con validación segura
        cliente = request.form.get("cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        subtotal = float(request.form.get("subtotal", 0))

        # Contrato único
        contrato = f"{datetime.now().year}-{int(datetime.utcnow().timestamp())}"

        # Guardar en PostgreSQL con manejo de errores
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO contratos (contrato, cliente, telefono, descripcion, subtotal, fecha)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (contrato, cliente, telefono, descripcion, subtotal, datetime.now()))
                conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f"Error guardando en DB: {e}")
            return render_template("formulario.html", contrato=None)

        #
