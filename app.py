from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from datetime import datetime
import io
import os
import boto3
import psycopg2
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# -------------------------------------------------
# APP
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret")

# -------------------------------------------------
# DATABASE (Render PostgreSQL)
# -------------------------------------------------
DATABASE_URL = os.environ["DATABASE_URL"]

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def init_db():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contratos (
                id SERIAL PRIMARY KEY,
                contrato TEXT UNIQUE NOT NULL,
                cliente TEXT NOT NULL,
                telefono TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                subtotal NUMERIC NOT NULL,
                fecha TIMESTAMP NOT NULL
            )
        """)

init_db()

# -------------------------------------------------
# AWS S3
# -------------------------------------------------
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=os.environ["AWS_REGION"]
)

S3_BUCKET = os.environ["S3_BUCKET"]

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        cliente = request.form.get("cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        subtotal = float(request.form.get("subtotal", 0))

        if not cliente or not telefono or not descripcion or subtotal <= 0:
            flash("Todos los campos son obligatorios")
            return redirect(url_for("index"))

        contrato = f"{datetime.now().year}-{int(datetime.utcnow().timestamp())}"

        # Guardar en DB
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO contratos (contrato, cliente, telefono, descripcion, subtotal, fecha)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (contrato, cliente, telefono, descripcion, subtotal, datetime.now()))

        # Generar PDF
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, 800, f"Contrato: {contrato}")

        pdf.setFont("Helvetica", 12)
        pdf.drawString(50, 770, f"Cliente: {cliente}")
        pdf.drawString(50, 750, f"Teléfono: {telefono}")
        pdf.drawString(50, 730, f"Descripción: {descripcion}")
        pdf.drawString(50, 710, f"Subtotal: ${subtotal:,.2f}")
        pdf.drawString(50, 690, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")

        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        # Subir a S3
        s3.upload_fileobj(
            buffer,
            S3_BUCKET,
            f"contratos/{contrato}.pdf",
            ExtraArgs={"ContentType": "application/pdf"}
        )

        flash(f"Contrato {contrato} generado correctamente")
        return render_template("formulario.html", contrato=contrato)

    return render_template("formulario.html", contrato=None)


@app.route("/descargar/<contrato>")
def descargar(contrato):
    buffer = io.BytesIO()
    s3.download_fileobj(
        S3_BUCKET,
        f"contratos/{contrato}.pdf",
        buffer
    )
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{contrato}.pdf")


# -------------------------------------------------
# MAIN (local only)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
