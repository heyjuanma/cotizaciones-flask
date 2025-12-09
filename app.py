import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

# ===========================
# DATABASE (Render)
# ===========================
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ===========================
# MODEL
# ===========================
class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    cliente = db.Column(db.String(120), nullable=False)
    total = db.Column(db.Float, nullable=False)

with app.app_context():
    db.create_all()

# ===========================
# ROUTES
# ===========================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        cliente = request.form.get("cliente", "").strip()
        total = request.form.get("total", 0)

        if cliente and total:
            ultimo = db.session.query(func.max(Cotizacion.numero)).scalar()
            nuevo_numero = 1 if ultimo is None else ultimo + 1

            cotizacion = Cotizacion(
                numero=nuevo_numero,
                cliente=cliente,
                total=float(total)
            )
            db.session.add(cotizacion)
            db.session.commit()

            return redirect(url_for("index"))

    cotizaciones = Cotizacion.query.order_by(Cotizacion.numero.desc()).all()
    return render_template("index.html", cotizaciones=cotizaciones)
