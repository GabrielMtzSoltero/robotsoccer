import os
import math
import random
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave_secreta_torneo'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///torneo.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)

# ----------------------------------------------------------------------
# MODELOS DE BASE DE DATOS
# ----------------------------------------------------------------------
class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)
    integrante1 = db.Column(db.String(80), nullable=False)
    integrante2 = db.Column(db.String(80), nullable=False)
    escudo = db.Column(db.String(200), nullable=False)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo.id'), nullable=True)

class Grupo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(10), nullable=False)
    equipos = db.relationship('Equipo', backref='grupo', lazy=True)
    partidos = db.relationship('PartidoGrupo', backref='grupo', lazy=True)

class PartidoGrupo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey('grupo.id'), nullable=False)
    jornada = db.Column(db.Integer, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=False)
    visita_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=False)
    gl = db.Column(db.Integer, nullable=True)
    gv = db.Column(db.Integer, nullable=True)

    local = db.relationship('Equipo', foreign_keys=[local_id])
    visita = db.relationship('Equipo', foreign_keys=[visita_id])

class PartidoKO(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ronda = db.Column(db.Integer, nullable=False)  # 1: 1/8s o 1/4s, etc.
    nombre_ronda = db.Column(db.String(50), nullable=False)
    posicion = db.Column(db.Integer, nullable=False)
    local_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=True)
    visita_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=True)
    gl = db.Column(db.Integer, nullable=True)
    gv = db.Column(db.Integer, nullable=True)
    pen_l = db.Column(db.Integer, nullable=True)
    pen_v = db.Column(db.Integer, nullable=True)
    ganador_id = db.Column(db.Integer, db.ForeignKey('equipo.id'), nullable=True)

    local = db.relationship('Equipo', foreign_keys=[local_id])
    visita = db.relationship('Equipo', foreign_keys=[visita_id])
    ganador = db.relationship('Equipo', foreign_keys=[ganador_id])

# ----------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------------------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def calcular_tabla(grupo):
    stats = {e.id: {'equipo': e, 'pj': 0, 'g': 0, 'e': 0, 'p': 0, 'gf': 0, 'gc': 0, 'dg': 0, 'pts': 0} for e in grupo.equipos}
    for p in grupo.partidos:
        if p.gl is not None and p.gv is not None:
            l, v = stats[p.local_id], stats[p.visita_id]
            l['pj'] += 1; v['pj'] += 1
            l['gf'] += p.gl; l['gc'] += p.gv
            v['gf'] += p.gv; v['gc'] += p.gl
            l['dg'] = l['gf'] - l['gc']
            v['dg'] = v['gf'] - v['gc']
            if p.gl > p.gv:
                l['g'] += 1; l['pts'] += 3; v['p'] += 1
            elif p.gl < p.gv:
                v['g'] += 1; v['pts'] += 3; l['p'] += 1
            else:
                l['e'] += 1; v['e'] += 1; l['pts'] += 1; v['pts'] += 1
    
    tabla = list(stats.values())
    tabla.sort(key=lambda x: (-x['pts'], -x['dg'], -x['gf'], x['equipo'].nombre.lower()))
    return tabla

# ----------------------------------------------------------------------
# RUTAS DE LA APLICACIÓN
# ----------------------------------------------------------------------
@app.route('/')
def index():
    return redirect(url_for('equipos'))

@app.route('/equipos', methods=['GET', 'POST'])
def equipos():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        int1 = request.form.get('integrante1', '').strip()
        int2 = request.form.get('integrante2', '').strip()
        file = request.files.get('escudo')

        if not nombre or not int1 or not int2 or not file:
            flash('Todos los campos son obligatorios.', 'danger')
        elif Equipo.query.filter(Equipo.nombre.ilike(nombre)).first():
            flash('Ya existe un equipo con ese nombre.', 'warning')
        elif file and allowed_file(file.filename):
            fn = secure_filename(file.filename)
            ext = fn.rsplit('.', 1)[1].lower()
            filename = f"{secure_filename(nombre.lower())}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            nuevo = Equipo(nombre=nombre, integrante1=int1, integrante2=int2, escudo=filename)
            db.session.add(nuevo)
            db.session.commit()
            flash('Equipo registrado exitosamente.', 'success')
            return redirect(url_for('equipos'))

    lista_equipos = Equipo.query.all()
    hay_grupos = Grupo.query.count() > 0
    return render_template('equipos.html', equipos=lista_equipos, hay_grupos=hay_grupos)

@app.route('/sortear_grupos')
def sortear_grupos():
    equipos = Equipo.query.all()
    n = len(equipos)
    if n < 3:
        flash('Se requieren al menos 3 equipos para iniciar el torneo.', 'warning')
        return redirect(url_for('equipos'))

    # Limpiar estado anterior
    PartidoKO.query.delete()
    PartidoGrupo.query.delete()
    Grupo.query.delete()
    for e in equipos:
        e.grupo_id = None
    db.session.commit()

    random.shuffle(equipos)
    num_grupos = math.ceil(n / 4)
    
    for k in range(num_grupos):
        g = Grupo(nombre=f"Grupo {chr(65 + k)}")
        db.session.add(g)
    db.session.commit()

    grupos = Grupo.query.all()
    for i, eq in enumerate(equipos):
        eq.grupo_id = grupos[i % num_grupos].id
    db.session.commit()

    # Generar calendario por grupo
    for g in grupos:
        eqs = g.equipos
        m = len(eqs)
        for i in range(m):
            for j in range(i + 1, m):
                p = PartidoGrupo(grupo_id=g.id, jornada=1, local_id=eqs[i].id, visita_id=eqs[j].id)
                db.session.add(p)
    db.session.commit()

    flash('Grupos sorteados con éxito.', 'success')
    return redirect(url_for('grupos'))

@app.route('/grupos', methods=['GET', 'POST'])
def grupos():
    if request.method == 'POST':
        partido_id = request.form.get('partido_id')
        gl = request.form.get('gl')
        gv = request.form.get('gv')
        p = PartidoGrupo.query.get(partido_id)
        if p and gl != '' and gv != '':
            p.gl = int(gl)
            p.gv = int(gv)
            db.session.commit()
            flash('Resultado guardado.', 'success')
        return redirect(url_for('grupos'))

    lista_grupos = Grupo.query.all()
    tablas = {g.id: calcular_tabla(g) for g in lista_grupos}
    
    # Verificar si todos los partidos de grupos han finalizado
    pendientes = PartidoGrupo.query.filter((PartidoGrupo.gl == None) | (PartidoGrupo.gv == None)).count()
    listo_para_ko = (len(lista_grupos) > 0) and (pendientes == 0)

    return render_template('grupos.html', grupos=lista_grupos, tablas=tablas, listo_para_ko=listo_para_ko)

@app.route('/generar_llaves')
def generar_llaves():
    grupos = Grupo.query.all()
    if not grupos:
        return redirect(url_for('equipos'))

    # Seleccionar clasificados
    clasificados = []
    segundos = []

    for g in grupos:
        tabla = calcular_tabla(g)
        if len(tabla) >= 1:
            clasificados.append(tabla[0]['equipo'])
        if len(tabla) >= 2:
            segundos.append(tabla[1])

    # Ordenar los segundos lugares por rendimiento para elegir los mejores si es necesario
    segundos.sort(key=lambda x: (-x['pts'], -x['dg'], -x['gf']))
    
    # Determinar cuántos entran según potencia de 2 más cercana (2, 4, 8, 16)
    total_base = len(clasificados)
    objetivo_llave = 2
    while objetivo_llave < total_base:
        objetivo_llave *= 2

    # Si faltan equipos para la llave, agregar los mejores segundos
    i = 0
    while len(clasificados) < objetivo_llave and i < len(segundos):
        clasificados.append(segundos[i]['equipo'])
        i += 1

    # Crear cuadro eliminatorio (Ronda 1)
    PartidoKO.query.delete()
    db.session.commit()

    random.shuffle(clasificados)
    n = len(clasificados)
    
    nombre_r = "Final" if n == 2 else ("Semifinales" if n == 4 else ("Cuartos de final" if n == 8 else f"Ronda de {n}"))

    for k in range(0, n, 2):
        loc = clasificados[k]
        vis = clasificados[k+1] if (k+1) < n else None
        p = PartidoKO(ronda=1, nombre_ronda=nombre_r, posicion=k//2, local_id=loc.id, visita_id=vis.id if vis else None)
        if vis is None:  # Bye
            p.ganador_id = loc.id
        db.session.add(p)
    
    db.session.commit()
    flash('Fase de eliminación directa generada.', 'success')
    return redirect(url_for('eliminatoria'))

@app.route('/eliminatoria', methods=['GET', 'POST'])
def eliminatoria():
    if request.method == 'POST':
        partido_id = request.form.get('partido_id')
        gl = int(request.form.get('gl', 0))
        gv = int(request.form.get('gv', 0))
        pen_l = request.form.get('pen_l')
        pen_v = request.form.get('pen_v')

        p = PartidoKO.query.get(partido_id)
        if p:
            p.gl = gl
            p.gv = gv
            if gl > gv:
                p.ganador_id = p.local_id
            elif gv > gl:
                p.ganador_id = p.visita_id
            else:
                p.pen_l = int(pen_l) if pen_l else 0
                p.pen_v = int(pen_v) if pen_v else 0
                p.ganador_id = p.local_id if p.pen_l > p.pen_v else p.visita_id
            
            db.session.commit()
            
            # Propagar ganador a la siguiente ronda
            propagar_ganador(p)
            flash('Resultado de eliminatoria actualizado.', 'success')

        return redirect(url_for('eliminatoria'))

    partidos = PartidoKO.query.order_by(PartidoKO.ronda, PartidoKO.posicion).all()
    return render_template('eliminatoria.html', partidos=partidos)

def propagar_ganador(partido_actual):
    sig_ronda = partido_actual.ronda + 1
    sig_posicion = partido_actual.posicion // 2
    es_local = (partido_actual.posicion % 2 == 0)

    sig_partido = PartidoKO.query.filter_by(ronda=sig_ronda, posicion=sig_posicion).first()
    
    if not sig_partido:
        # Contar cuántos partidos hay en la ronda actual para ver si sigue la final
        total_ronda = PartidoKO.query.filter_by(ronda=partido_actual.ronda).count()
        if total_ronda > 1:
            nom_sig = "Final" if total_ronda == 2 else f"Ronda {sig_ronda}"
            sig_partido = PartidoKO(ronda=sig_ronda, nombre_ronda=nom_sig, posicion=sig_posicion)
            db.session.add(sig_partido)

    if sig_partido:
        if es_local:
            sig_partido.local_id = partido_actual.ganador_id
        else:
            sig_partido.visita_id = partido_actual.ganador_id
        db.session.commit()

@app.route('/reiniciar')
def reiniciar():
    PartidoKO.query.delete()
    PartidoGrupo.query.delete()
    Grupo.query.delete()
    Equipo.query.delete()
    db.session.commit()
    flash('Se han borrado todos los datos del torneo.', 'info')
    return redirect(url_for('equipos'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)