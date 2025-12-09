from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from datetime import datetime
import io
import os
import boto3
import psycopg2
import traceback
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret")

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def get_db_connection():
    try:
        return psycopg2.connect(os.environ.get("DATABASE_URL"))
    except Exception as e:
        print("DB CONNECTION ERROR:")
        traceback.print_exc()
        return None


def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
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
        conn.close()
    except Exception:
        print("DB INIT ERROR:")
        traceback.print_exc()


def get_s3_client():
    try:
        return boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION")
        )
    except Exception:
        print("S3 CLIENT ERROR:")
        traceback.print_exc()
        return None


# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    init_db()

    if request.method == "POST":
        try:
            cliente = request.form.get("cliente", "").strip()
            telefono = request.form.get("telefono", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            subtotal = float(request.form.get("subtotal", 0))

            contrato = f"{datetime.now().year}-{int(datetime.utcnow().timestamp())}"

            # DB SAVE
            conn = get_db_connection()
            if not conn:
                flash("Error de base de datos")
                return redirect(url_for("index"))

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO contratos (contrato, cliente, telefono, descripcion, subtotal, fecha)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (contrato, cliente, telefono, descripcion, subtotal, datetime.now()))
            conn.commit()
            conn.close()

            # PDF
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            pdf.setFont("Helvetica", 12)
            pdf.drawString(50, 800, f"Contrato: {contrato}")
            pdf.drawString(50, 770, f"Cliente: {cliente}")
            pdf.drawString(50, 740, f"Subtotal: ${subtotal:,.2f}")
            pdf.save()
            buffer.seek(0)

            # S3
            s3 = get_s3_client()
            if not s3:
                flash("Error conectando a S3")
                return redirect(url_for("index"))

            bucket = os.environ.get("S3_BUCKET")
            s3.upload_fileobj(buffer, bucket, f"contratos/{contrato}.pdf")

            flash(f"Contrato {contrato} generado")
            return render_template("formulario.html", contrato=contrato)

        except Exception:
            print("POST ERROR:")
            traceback.print_exc()
            flash("Error interno")
            return redirect(url_for("index"))

    return render_template("formulario.html", contrato=None)


@app.route("/descargar/<contrato>")
def descargar(contrato):
    try:
        s3 = get_s3_client()
        buffer = io.BytesIO()
        s3.download_fileobj(
            os.environ.get("S3_BUCKET"),
            f"contratos/{contrato}.pdf",
            buffer
        )
        buffer.seek(0)
        return send_file(buffer, as_attachment=True)
    except Exception:
        print("DOWNLOAD ERROR:")
        traceback.print_exc()
        flash("No se pudo descargar el PDF")
        return redirect(url_for("index"))


# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
