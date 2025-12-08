from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from datetime import datetime
import io
import boto3
import psycopg2
from reportlab.pdfgen import canvas

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
        # Campos del formulario con validación segura
        cliente = request.form.get("cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        subtotal = float(request.form.get("subtotal", 0))

        # Generar contrato único
        contrato = f"{datetime.now().year}-{int(datetime.utcnow().timestamp())}"

        # Guardar en PostgreSQL
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO contratos (contrato, cliente, telefono, descripcion, subtotal)
                VALUES (%s, %s, %s, %s, %s)
            """, (contrato, cliente, telefono, descripcion, subtotal))
            conn.commit()

        # Generar PDF en memoria
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer)
        c.drawString(100, 800, f"Contrato: {contrato}")
        c.drawString(100, 780, f"Cliente: {cliente}")
        c.drawString(100, 760, f"Teléfono: {telefono}")
        c.drawString(100, 740, f"Descripción: {descripcion}")
        c.drawString(100, 720, f"Subtotal: {subtotal}")
        c.save()
        pdf_buffer.seek(0)

        # Guardar PDF en S3
        s3_client.upload_fileobj(
            pdf_buffer,
            S3_BUCKET,
            f"contratos/{contrato}.pdf",
            ExtraArgs={"ContentType": "application/pdf"}
        )

        flash(f"Contrato {contrato} generado correctamente.")
        return render_template("formulario.html", contrato=contrato)

    return render_template("formulario.html", contrato=None)

@app.route("/descargar/<contrato>")
def descargar(contrato):
    pdf_buffer = io.BytesIO()
    # Descargar desde S3
    s3_client.download_fileobj(S3_BUCKET, f"contratos/{contrato}.pdf", pdf_buffer)
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, as_attachment=True, download_name=f"{contrato}.pdf")

if __name__ == "__main__":
    app.run(debug=True)
