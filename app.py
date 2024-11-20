import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gastos_comunes.db'  # Base de datos SQLite
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo Departamento
class Departamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    monto_diferenciado = db.Column(db.Integer, default=200000)

    def __repr__(self):
        return f"<Departamento {self.numero}>"

# Modelo GastoComún
class GastoComún(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamento.id'), nullable=False)
    periodo = db.Column(db.String(7), nullable=False)  # Año-Mes
    monto = db.Column(db.Integer, nullable=False)
    pagado = db.Column(db.Boolean, default=False)
    fecha_pago = db.Column(db.Date, nullable=True)

    departamento = db.relationship('Departamento', backref=db.backref('gastos', lazy=True))

    def marcar_como_pagado(self, fecha_pago):
        if self.pagado:
            return "Pago duplicado"
        
        fecha_limite = datetime.strptime(self.periodo, "%Y-%m")
        ultimo_dia_mes = (fecha_limite.replace(month=fecha_limite.month % 12 + 1) - timedelta(days=1)).day
        fecha_limite = fecha_limite.replace(day=ultimo_dia_mes)

        estado_pago = "Pago exitoso dentro del plazo" if fecha_pago <= fecha_limite else "Pago exitoso fuera de plazo"
        
        self.pagado = True
        self.fecha_pago = fecha_pago
        db.session.commit()
        return estado_pago

# Crear tablas en la base de datos dentro del contexto de la aplicación
with app.app_context():
    db.create_all()

# Sistema de Gastos Comunes
class SistemaGastosComunes:
    def agregar_departamento(self, numero, monto_diferenciado=None):
        if Departamento.query.filter_by(numero=numero).first():
            return {"error": "El departamento ya existe."}
        nuevo_departamento = Departamento(numero=numero, monto_diferenciado=monto_diferenciado)
        db.session.add(nuevo_departamento)
        db.session.commit()
        return {"mensaje": f"Departamento {numero} agregado."}

    def generar_gastos_comunes_mes(self, mes, anio):
        gastos_generados = []
        periodo = f"{anio}-{mes:02d}"  # Formato de periodo: Año-Mes (Ej: "2024-11")
        departamentos = Departamento.query.all()
        for depto in departamentos:
            if not GastoComún.query.filter_by(departamento_id=depto.id, periodo=periodo).first():
                gasto = GastoComún(departamento_id=depto.id, periodo=periodo, monto=depto.monto_diferenciado)
                db.session.add(gasto)
                db.session.commit()
                gastos_generados.append({
                    "departamento": depto.numero,
                    "periodo": periodo,
                    "monto": f"${gasto.monto:,.0f} CLP"
                })
        
        return {
            "accion": "Listado de gastos generados",
            "mes": f"{mes}",
            "año": anio,
            "gastos_generados": gastos_generados
        }

    def generar_gastos_comunes_anio(self, anio):
        gastos_generados = []
        for mes in range(1, 13):  # Genera un gasto por cada mes del año
            resultado_mes = self.generar_gastos_comunes_mes(mes, anio)
            gastos_generados.extend(resultado_mes["gastos_generados"])
        
        return {
            "accion": "Listado de gastos generados",
            "año": anio,
            "gastos_generados": gastos_generados
        }

    def marcar_pago(self, numero_departamento, mes, anio, fecha_pago):
        departamento = Departamento.query.filter_by(numero=numero_departamento).first()
        if not departamento:
            return {"error": "Departamento no encontrado"}

        periodo = f"{anio}-{mes:02d}"
        gasto = GastoComún.query.filter_by(departamento_id=departamento.id, periodo=periodo, pagado=False).first()

        if gasto:
            estado_pago = gasto.marcar_como_pagado(fecha_pago)
            return {
                "departamento": numero_departamento,
                "fecha_pago": fecha_pago.strftime('%Y-%m-%d'),
                "periodo": periodo,
                "estado_pago": estado_pago
            }
        return {"error": "Gasto no encontrado o ya pagado"}

    def obtener_gastos_pendientes(self, mes, anio):
        gastos_pendientes = GastoComún.query.filter(GastoComún.pagado == False, GastoComún.periodo <= f"{anio}-{mes:02d}").all()
        if gastos_pendientes:
            gastos_pendientes_info = [
                {"departamento": gasto.departamento.numero, "periodo": gasto.periodo, "monto": f"${gasto.monto:,.0f} CLP"}
                for gasto in gastos_pendientes
            ]
            return {
                "accion": "Listado de gastos pendientes",
                "mes": f"{mes}",
                "año": anio,
                "gastos_pendientes": gastos_pendientes_info
            }
        else:
            return {
                "accion": "Listado de gastos pendientes",
                "mes": f"{mes}",
                "año": anio,
                "gastos_pendientes": "Sin montos pendientes"
            }

# Instanciamos el sistema
sistema = SistemaGastosComunes()

@app.route('/departamento', methods=['POST'])
def agregar_departamento():
    data = request.get_json()
    numero = data.get('numero')
    monto_diferenciado = data.get('monto_diferenciado')
    resultado = sistema.agregar_departamento(numero, monto_diferenciado)
    return jsonify(resultado), 201

@app.route('/gastos/comunes', methods=['POST'])
def generar_gastos_comunes():
    data = request.get_json()
    mes = data.get('mes')
    anio = data.get('anio')

    if anio and not mes:
        resultado = sistema.generar_gastos_comunes_anio(anio)
    elif mes and anio:
        resultado = sistema.generar_gastos_comunes_mes(mes, anio)
    else:
        return jsonify({"error": "Debe proporcionar el mes y el año."}), 400
    
    return jsonify(resultado), 200

@app.route('/pago', methods=['POST'])
def marcar_pago():
    data = request.get_json()
    numero_departamento = data.get('numero_departamento')
    mes = data.get('mes')
    anio = data.get('anio')
    fecha_pago_str = data.get('fecha_pago')
    fecha_pago = datetime.strptime(fecha_pago_str, '%Y-%m-%d')
    resultado = sistema.marcar_pago(numero_departamento, mes, anio, fecha_pago)
    return jsonify(resultado), 200

@app.route('/gastos/pendientes', methods=['GET'])
def obtener_gastos_pendientes():
    mes = request.args.get('mes', type=int)
    anio = request.args.get('anio', type=int)
    resultado = sistema.obtener_gastos_pendientes(mes, anio)
    return jsonify(resultado), 200

if __name__ == '__main__':
    app.run(debug=True)
