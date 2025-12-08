from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from datetime import datetime
import io
import os
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecreto")

# --- Configuración S3 ---
S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ["S3_REGION"]
AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]

s3_client = boto3.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# --- Configuración PostgreSQL ---
DB_HOST = os.environ["DB_HOST"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )
    conn.autocommit = True
except Exception as e:
    print("ERROR conectando a PostgreSQL:", e)
    raise

# --- Ruta principal ---
@app.route("/", methods=["GET", "POST"])
def formulario():
    if request.method == "POST":
        # Obtener campos de forma segura
        cliente = request.form.get("cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        subtotal = float(request.form.get("subtotal", 0))

        # Generar contrato único
        contrato = f"{datetime.now().year}-{int(datetime.utcnow().timestamp())}"

        # Guardar en PostgreSQL
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contratos (
                        id SERIAL PRIMARY KEY,
                        contrato VARCHAR(50) UNIQUE,
                        cliente TEXT,
                        telefono TEXT,
                        descripcion TEXT,
                        subtotal NUMERIC,
                        fecha TIMESTAMP
                    );
                """)
                cur.execute("""
                    INSERT INTO contratos (contrato, cliente, telefono, descripcion, subtotal, fecha)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (contrato, cliente, telefono, descripcion, subtotal, datetime.now()))
        except Exception as e:
            flash(f"Error guardando en la base de datos: {e}")
            return render_template("formulario.html", contrato=None)

        # Generar PDF
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4

        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"Contrato: {contrato}")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")

        # Tabla con los datos
        data = [
            ["Cliente", cliente],
            ["Teléfono", telefono],
            ["Descripción", descripcion],
            ["Subtotal", f"${subtotal:,.2f}"]
        ]
        table = Table(data, colWidths=[100*mm, 80*mm])
        style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('BACKGROUND',(0,1),(-1,-1),colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ])
        table.setStyle(style)
        table.wrapOn(c, width, height)
        table.drawOn(c, 50, height - 200)

        c.showPage()
        c.save()
        pdf_buffer.seek(0)

        # Subir PDF a S3
        try:
            s3_client.upload_fileobj(
                pdf_buffer,
                S3_BUCKET,
                f"contratos/{contrato}.pdf",
                ExtraArgs={"ContentType": "application/pdf"}
            )
        except Exception as e:
            flash(f"Error subiendo PDF a S3: {e}")
            return render_template("formulario.html", contrato=None)

        flash(f"Contrato {contrato} generado correctamente.")
        return render_template("formulario.html", contrato=contrato)

    return render_template("formulario.html", contrato=None)

# --- Descargar PDF ---
@app.route("/descargar/<contrato>")
def descargar(contrato):
    pdf_buffer = io.BytesIO()
    try:
        s3_client.download_fileobj(S3_BUCKET, f"contratos/{contrato}.pdf", pdf_buffer)
        pdf_buffer.seek(0)
        return send_file(pdf_buffer, as_attachment=True, download_name=f"{contrato}.pdf")
    except Exception as e:
        flash(f"No se pudo descargar el PDF: {e}")
        return redirect(url_for("formulario"))

if __name__ == "__main__":
    app.run(debug=True)
