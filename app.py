import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

# =====================================================
# CONFIGURACIÓN DE BASE DE DATOS (RENDER POSTGRES)
# =====================================================
DATABASE_URL = os.environ.get("DATABASE_URL")

# Render usa "postgres://", SQLAlchemy requiere "postgresql://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =====================================================
# MODELO
# =====================================================
class Cotizacion(db.Model):
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero_registro = db.Column(db.Integer, unique=True, nullable=False)
    cliente = db.Column(db.String(120), nullable=False)
    total = db.Column(db.Float, nullable=False)

# =====================================================
# CREAR TABLAS AUTOMÁTICAMENTE
# =====================================================
with app.app_context():
    db.create_all()

# =====================================================
# RUTAS
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "OK",
        "message": "API de cotizaciones funcionando"
    })

@app.route("/cotizaciones", methods=["POST"])
def crear_cotizacion():
    data = request.get_json()

    if not data or "cliente" not in data or "total" not in data:
        return jsonify({"error": "Datos incompletos"}), 400

    ultimo_numero = db.session.query(
        func.max(Cotizacion.numero_registro)
    ).scalar()

    nuevo_numero = 1 if ultimo_numero is None else ultimo_numero + 1

    nueva = Cotizacion(
        numero_registro=nuevo_numero,
        cliente=data["cliente"],
        total=float(data["total"])
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
    cotizaciones = Cotizacion.query.order_by(
        Cotizacion.numero_registro.desc()
    ).all()

    resultado = []
    for c in cotizaciones:
        resultado.append({
            "id": c.id,
            "numero_registro": c.numero_registro,
            "cliente": c.cliente,
            "total": c.total
        })

    return jsonify(resultado)
