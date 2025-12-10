from flask import Flask, render_template, request, send_file
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from datetime import datetime
import os

app = Flask(__name__)

def generar_numero_contrato():
    hoy = datetime.now().strftime("%Y-%m-%d")
    contador_path = "contador.txt"

    if not os.path.exists(contador_path):
        with open(contador_path, "w") as f:
            f.write("0")

    with open(contador_path, "r+") as f:
        contador = int(f.read()) + 1
        f.seek(0)
        f.write(str(contador))
        f.truncate()

    return f"{hoy}-{contador:04d}"

@app.route("/", methods=["GET", "POST"])
def formulario():
    if request.method == "POST":
        data = request.form
        contrato = generar_numero_contrato()
        fecha = datetime.now().strftime("%d/%m/%Y")

        file_path = f"contrato_{contrato}.pdf"
        doc = SimpleDocTemplate(file_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # LOGO
        logo_path = os.path.join(app.root_path, "static", "logo.png")
        elements.append(Image(logo_path, width=150, height=70))
        elements.append(Spacer(1, 10))

        # CONTRATO
        elements.append(Paragraph(
            f"<font color='red' size='16'><b>Contrato número: {contrato}</b></font>",
            styles["Normal"]
        ))
        elements.append(Spacer(1, 10))

        elements.append(Paragraph(f"<b>Nombre del Cliente:</b> {data['cliente']}", styles["Normal"]))
        elements.append(Paragraph(f"<b>Contacto:</b> {data['contacto']}", styles["Normal"]))
        elements.append(Paragraph(f"<b>Email:</b> {data['email']}", styles["Normal"]))
        elements.append(Paragraph(
            f"<b>Teléfono:</b> {data['telefono']} &nbsp;&nbsp;&nbsp; "
            f"<b>Fecha de contrato:</b> {fecha}",
            styles["Normal"]
        ))
        elements.append(Paragraph(
            "<b>Días de entrega:</b> 15 Días &nbsp;&nbsp;&nbsp; "
            "<b>Vigencia del contrato:</b> 15 Días",
            styles["Normal"]
        ))

        elements.append(Spacer(1, 15))

        # TITULO
        elements.append(Paragraph(
            "<b><u>TÍTULO</u></b>",
            ParagraphStyle(name="titulo", alignment=TA_CENTER, fontSize=14)
        ))

        elements.append(Spacer(1, 10))

        # CUADRO DESCRIPCIÓN
        elements.append(Table(
            [[Paragraph(data["descripcion"], styles["Normal"])]],
            colWidths=[500],
            style=[('BOX', (0,0), (-1,-1), 1, colors.black)]
        ))

        elements.append(Spacer(1, 15))

        # TABLA ITEMS (SIN IMPUESTO)
        tabla_data = [["Cantidad", "Detalle", "Precio Unit.", "Monto"]]

        subtotal = 0
        for i in range(len(data.getlist("cantidad[]"))):
            cant = float(data.getlist("cantidad[]")[i])
            precio = float(data.getlist("precio[]")[i])
            monto = cant * precio
            subtotal += monto

            tabla_data.append([
                f"{cant:.2f}",
                data.getlist("detalle[]")[i],
                f"{precio:.2f}",
                f"{monto:.2f}"
            ])

        tabla = Table(tabla_data, colWidths=[60, 240, 80, 80])
        tabla.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)
        ]))

        elements.append(tabla)
        elements.append(Spacer(1, 15))

        # NOTAS + TOTALES
        notas = Paragraph(
            "Pagadera en colones al tipo de cambio de la fecha de cancelación de la factura "
            "según el tipo de cambio para la venta del Banco Central de Costa Rica.<br/><br/>"
            "<b>Forma de Pago: 50% de prima, cancelación contra entrega.</b>",
            styles["Normal"]
        )

        totales = Table([
            ["Subtotal", f"{subtotal:.2f}"],
            ["Impuesto", "0.00"],
            ["Total", f"{subtotal:.2f}"]
        ], colWidths=[80,80])

        totales.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))

        elements.append(Table([[notas, totales]], colWidths=[320,160]))
        elements.append(Spacer(1, 40))

        # FIRMA
        elements.append(Paragraph(
            "<b>Firma autorizada</b><br/>Juan Freer Bustamante<br/>Gerente General",
            styles["Normal"]
        ))

        doc.build(elements)
        return send_file(file_path, as_attachment=True)

    return render_template("formulario.html")

if __name__ == "__main__":
    app.run(debug=True)
