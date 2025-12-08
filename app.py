from flask import Flask, render_template, request, send_file
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import os

app = Flask(__name__)

# -------------------------
# CREAR CARPETA pdfs
# -------------------------
if not os.path.exists("pdfs"):
    os.makedirs("pdfs")

# -------------------------
# LIMPIAR NOMBRE DEL CLIENTE
# -------------------------
def nombre_seguro(nombre):
    limpio = ""
    for c in nombre:
        if c.isalnum() or c in (" ", "_"):
            limpio += c
    return limpio.strip().replace(" ", "_").upper()

# -------------------------
# BASE DE DATOS
# -------------------------
def db():
    conn = sqlite3.connect("database.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato TEXT,
            cliente TEXT,
            telefono TEXT,
            descripcion TEXT,
            subtotal REAL,
            iva REAL,
            total REAL,
            fecha TEXT
        )
    """)
    return conn

# -------------------------
# RUTA PRINCIPAL
# -------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        cliente = request.form["cliente"]
        telefono = request.form["telefono"]
        descripcion = request.form["descripcion"]
        subtotal = float(request.form["subtotal"])

        iva = subtotal * 0.13
        total = subtotal + iva
        fecha = datetime.now().strftime("%d/%m/%Y")

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO cotizaciones
            (cliente, telefono, descripcion, subtotal, iva, total, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cliente, telefono, descripcion, subtotal, iva, total, fecha))

        cot_id = cur.lastrowid
        contrato = f"{datetime.now().year}-{cot_id:05d}"

        cur.execute(
            "UPDATE cotizaciones SET contrato=? WHERE id=?",
            (contrato, cot_id)
        )

        conn.commit()
        conn.close()

        generar_pdf(
            contrato,
            cliente,
            telefono,
            descripcion,
            subtotal,
            iva,
            total,
            fecha
        )

        carpeta_cliente = nombre_seguro(cliente)
        ruta_pdf = os.path.join("pdfs", carpeta_cliente, f"{contrato}.pdf")

        return send_file(ruta_pdf, as_attachment=True)

    return render_template("formulario.html")

# -------------------------
# GENERAR PDF
# -------------------------
def generar_pdf(contrato, cliente, telefono, descripcion, subtotal, iva, total, fecha):
    carpeta_cliente = nombre_seguro(cliente)
    ruta_cliente = os.path.join("pdfs", carpeta_cliente)

    if not os.path.exists(ruta_cliente):
        os.makedirs(ruta_cliente)

    ruta_pdf = os.path.join(ruta_cliente, f"{contrato}.pdf")

    c = canvas.Canvas(ruta_pdf, pagesize=letter)
    c.setFont("Helvetica", 10)

    c.drawString(50, 740, "ROTULOS FREER S.A.")
    c.drawString(50, 725, "COTIZACIÓN / CONTRATO")
    c.drawString(400, 740, f"N° {contrato}")
    c.drawString(400, 725, f"Fecha: {fecha}")

    c.line(50, 715, 550, 715)

    c.drawString(50, 690, f"Cliente: {cliente}")
    c.drawString(50, 675, f"Teléfono: {telefono}")

    c.drawString(50, 640, "Descripción:")
    text = c.beginText(50, 625)
    for line in descripcion.split("\n"):
        text.textLine(line)
    c.drawText(text)

    c.line(50, 300, 550, 300)

    c.drawString(350, 275, f"Subtotal: ₡{subtotal:,.2f}")
    c.drawString(350, 260, f"IVA (13%): ₡{iva:,.2f}")
    c.drawString(350, 245, f"TOTAL: ₡{total:,.2f}")

    c.drawString(50, 200, "Forma de pago: 50% prima / saldo contra entrega")
    c.drawString(50, 180, "Pagadero en colones según tipo de cambio BCCR")

    c.drawString(50, 120, "Firma autorizada: __________________________")

    c.showPage()
    c.save()

# -------------------------
# EJECUTAR APLICACIÓN
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
