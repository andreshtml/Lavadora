import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import time

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v4.0", layout="wide", page_icon="🧺")

# --- CONEXIÓN A BASE DE DATOS ---
conn = sqlite3.connect('sistema_lavanderia_v4.db', check_same_thread=False)
c = conn.cursor()

def inicializar_db():
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, clave TEXT, rol TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes 
                 (id INTEGER PRIMARY KEY, nombre TEXT, tel TEXT, lat REAL, lon REAL, notas TEXT, fecha_registro DATETIME)''')
    c.execute('CREATE TABLE IF NOT EXISTS lavadoras (id INTEGER PRIMARY KEY, serie TEXT, modelo TEXT, estado TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS alquileres_activos 
                 (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, inicio DATETIME, fin DATETIME, 
                  horas_extras INTEGER DEFAULT 0, avisado INTEGER DEFAULT 0, repartidor_asig TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_alquileres 
                 (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, fecha DATETIME, 
                  monto REAL, tipo_pago TEXT, referencia TEXT, usuario_cobro TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, usuario TEXT, accion TEXT, fecha DATETIME)')
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera'), ('repartidor', 'ruta123', 'Repartidor')")
    conn.commit()

inicializar_db()

# --- VARIABLES DE ESTADO ---
if 'paso_actual' not in st.session_state:
    st.session_state.paso_actual = "Registro"

def registrar_log(accion):
    user = st.session_state.get('user', 'Sistema')
    c.execute("INSERT INTO logs (usuario, accion, fecha) VALUES (?,?,?)", (user, accion, datetime.now()))
    conn.commit()

# --- AUTENTICACIÓN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False

if not st.session_state['auth']:
    st.title("🔐 Acceso Empresarial")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Iniciar Sesión"):
        res = c.execute("SELECT rol FROM usuarios WHERE usuario=? AND clave=?", (u, p)).fetchone()
        if res:
            st.session_state.update({'auth': True, 'user': u, 'rol': res[0]})
            registrar_log("Inicio de Sesión")
            st.rerun()
        else: st.error("Credenciales incorrectas")
    st.stop()

rol_actual = st.session_state['rol']
user_active = st.session_state['user']

# --- MENÚ LATERAL ---
st.sidebar.title(f"👤 {user_active}")
menu = st.sidebar.selectbox("Menú Principal", ["🧺 Inventario Equipos", "👥 Clientes y Despacho", "⏱️ Control de Tiempos", "🚚 Logística Bodega", "📊 Reporte Admin", "⚙️ Configuración"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO 0: INVENTARIO ---
if menu == "🧺 Inventario Equipos":
    st.title("🧺 Gestión de Lavadoras")
    
    def guardar_lavadora():
        s, m = st.session_state.ser_in, st.session_state.mod_in
        if s and m:
            c.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
            conn.commit()
            st.toast("✅ Lavadora registrada")
        else: st.error("Llene los campos")

    with st.form("form_lav", clear_on_submit=True):
        c1, c2 = st.columns(2)
        c1.text_input("Número de Serie", key="ser_in")
        c2.text_input("Modelo / Marca", key="mod_in")
        st.form_submit_button("Registrar", on_click=guardar_lavadora)
    
    df_l = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
    st.dataframe(df_l, use_container_width=True)

# --- MÓDULO 1: CLIENTES Y DESPACHO (CORREGIDO) ---
elif menu == "👥 Clientes y Despacho":
    st.title("👥 Flujo de Salida de Equipos")

    # Control de navegación visual
    pasos = ["Registro", "Despacho"]
    idx_actual = pasos.index(st.session_state.paso_actual)
    nav = st.segmented_control("Etapa del Proceso", pasos, selection_mode="single", default=st.session_state.paso_actual)
    
    if nav: st.session_state.paso_actual = nav

    if st.session_state.paso_actual == "Registro":
        def procesar_cliente():
            nom, tel, gps, nota = st.session_state.cn, st.session_state.ct, st.session_state.cg, st.session_state.cnt
            if nom and tel:
                lat, lon = 0.0, 0.0
                coords = re.findall(r"([-+]?\d*\.\d+|\d+)", gps)
                if len(coords)>=2: lat, lon = float(coords[0]), float(coords[1])
                c.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                         (nom, tel, lat, lon, nota, datetime.now()))
                conn.commit()
                # SALTO AUTOMÁTICO A DESPACHO
                st.session_state.paso_actual = "Despacho"
                st.toast(f"✅ Cliente {nom} guardado correctamente")
            else: st.error("Datos incompletos")

        with st.form("reg_cli_flow", clear_on_submit=True):
            st.subheader("📝 Datos del Cliente")
            st.text_input("Nombre Completo", key="cn")
            st.text_input("WhatsApp", key="ct")
            st.text_input("Ubicación GPS", key="cg")
            st.text_area("Notas de Dirección", key="cnt")
            st.form_submit_button("🚀 Guardar Cliente y Continuar", on_click=procesar_cliente)

    else:
        st.subheader("📦 Asignación de Equipo y Repartidor")
        df_c = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
        df_l = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        df_r = pd.read_sql_query("SELECT usuario FROM usuarios WHERE rol='Repartidor'", conn)

        if not df_c.empty and not df_l.empty:
            c1, c2 = st.columns(2)
            # El cliente nuevo aparecerá de primero gracias al ORDER BY DESC
            cliente = c1.selectbox("👤 Cliente", df_c['nombre'])
            lavadora = c1.selectbox("🧺 Lavadora Disponible", df_l['serie'])
            reparto = c2.selectbox("🚚 Repartidor", df_r['usuario'])
            tiempo = c2.number_input("Horas de Alquiler", min_value=1, value=4)

            if st.button("🏁 Confirmar Despacho"):
                row_c = df_c[df_c['nombre'] == cliente].iloc[0]
                id_l = df_l[df_l['serie'] == lavadora]['id'].values[0]
                f_ini = datetime.now()
                f_fin = f_ini + timedelta(hours=tiempo)

                c.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin, repartidor_asig) VALUES (?,?,?,?,?)",
                         (row_c['id'], id_l, f_ini, f_fin, reparto))
                c.execute("UPDATE lavadoras SET estado='En Camino' WHERE id=?", (id_l,))
                conn.commit()

                st.success(f"¡Despacho registrado!")
                st.session_state.paso_actual = "Registro" # Reset para el siguiente
                st.rerun()
        else:
            st.warning("Debe registrar un cliente y tener lavadoras disponibles.")
            if st.button("Volver al Registro"):
                st.session_state.paso_actual = "Registro"
                st.rerun()

# --- MÓDULO 2: CONTROL Y COBRO ---
elif menu == "⏱️ Control de Tiempos":
    st.title("⏱️ Monitor en Tiempo Real")
    query = '''SELECT a.id, c.nombre, c.tel, l.serie, l.id as id_lav, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    activos = pd.read_sql_query(query, conn)

    if activos.empty:
        st.info("Sin equipos en uso.")
    else:
        for _, row in activos.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                f_fin = datetime.strptime(row['fin'], "%Y-%m-%d %H:%M:%S.%f")
                minutos = int((f_fin - datetime.now()).total_seconds() / 60)
                
                col1.write(f"**Cliente:** {row['nombre']} | **Lavadora:** {row['serie']}")
                if minutos > 0: col1.write(f"⏳ Quedan {minutos} min")
                else: col1.error(f"⚠️ Retraso de {abs(minutos)} min")

                if col2.button("💰 Cobrar", key=row['id']):
                    c.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto) VALUES (?,?,?,?)",
                             (row['id'], row['id_lav'], datetime.now(), 50.0))
                    c.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['id_lav'],))
                    c.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                    conn.commit(); st.rerun()

# --- OTROS MÓDULOS (SIMPLIFICADOS) ---
elif menu == "🚚 Logística Bodega":
    st.title("📥 Recepción de Equipos")
    df_ret = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    for _, l in df_ret.iterrows():
        if st.button(f"Confirmar Entrada {l['serie']}"):
            c.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
            conn.commit(); st.rerun()

elif menu == "📊 Reporte Admin":
    if rol_actual != "Admin": st.error("No autorizado"); st.stop()
    st.title("📊 Resumen")
    st.dataframe(pd.read_sql_query("SELECT * FROM historial_alquileres", conn))

elif menu == "⚙️ Configuración":
    if rol_actual != "Admin": st.error("No autorizado"); st.stop()
    if st.button("LIMPIAR BASE DE DATOS"):
        c.execute("DELETE FROM clientes"); c.execute("DELETE FROM alquileres_activos")
        c.execute("DELETE FROM lavadoras"); conn.commit(); st.rerun()
