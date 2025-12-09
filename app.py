import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

# ==============================
# CONFIGURACIÓN BASE DE DATOS
# ==============================
DATABASE_URL = os.environ.get("DATABASE_URL")

# Render usa postgres:// y SQLAlchemy necesita postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ==============================
# MODELOS
# ==============================
class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.Integer, unique=True, nullable=False)
    cliente = db.Column(db.String(120), nullable=False)
    total = db.Column(db.Float, nullable=False)

# ==============================
# INICIALIZAR DB
# ==============================
with app.app_context():
    db.create_all()

# ==============================
# RUTAS
# ==============================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Cotizaciones API"
    })

@app.route("/cotizaciones", methods=["POST"])
def crear_cotizacion():
    data = request.json

    ultimo = db.session.query(func.max(Cotizacion.numero_registro)).scalar()
    siguiente_numero = 1 if ultimo is None else ultimo + 1

    nueva = Cotizacion(
        numero_registro=siguiente_numero,
        cliente=data["cliente"],
        total=data["total"]
    )

    db.session.add(nueva)
    db.session.commit()

    return jsonify({
        "id": nueva.id,
        "numero_registro": nueva.numero_registro,
        "cliente": nueva.cliente,
        "total": nueva.total
    }), 201

@app.route("/cotizaciones", methods=["GET"])
def listar_cotizaciones():
    cotizaciones = Cotizacion.query.order_by(Cotizacion.numero_registro.desc()).all()

    return jsonify([
        {
            "id": c.id,
            "numero_registro": c.numero_registro,
            "cliente": c.cliente,
            "total": c.total
        }
        for c in cotizaciones
    ])
