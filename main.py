import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import time

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Lavandería Master Pro v4.0", layout="wide", page_icon="🧺")

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
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera'), ('repartidor', 'ruta123', 'Repartidor')")
    conn.commit()

inicializar_db()

# --- GESTIÓN DE NAVEGACIÓN Y LIMPIEZA ---
if 'radio_despacho' not in st.session_state:
    st.session_state.radio_despacho = "Registro"

def reset_despacho():
    """Limpia los campos de despacho forzando el reinicio del formulario"""
    st.session_state.radio_despacho = "Registro"
    st.rerun()

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
            st.rerun()
        else: st.error("Credenciales incorrectas")
    st.stop()

rol_actual = st.session_state['rol']
user_active = st.session_state['user']

# --- MENÚ LATERAL ---
st.sidebar.title(f"👤 {user_active}")
menu = st.sidebar.selectbox("Menú Principal", ["👥 Clientes y Despacho", "🧺 Inventario Equipos", "⏱️ Control de Tiempos", "🚚 Logística Bodega", "📊 Reporte Admin"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO: CLIENTES Y DESPACHO ---
if menu == "👥 Clientes y Despacho":
    st.title("👥 Gestión de Clientes y Salida")

    opcion = st.radio("Seleccione Acción:", ["Registro", "Despacho"], 
                      key="radio_despacho", 
                      horizontal=True)

    if opcion == "Registro":
        with st.form("reg_cli", clear_on_submit=True):
            st.subheader("➕ Registro Nuevo Cliente")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Ej: 58412...)")
            gps = st.text_input("Link Ubicación WhatsApp")
            nota = st.text_area("Notas de Dirección")
            if st.form_submit_button("Guardar y Ir a Despacho"):
                if nom and tel:
                    lat, lon = 0.0, 0.0
                    coords = re.findall(r"([-+]?\d*\.\d+|\d+)", gps)
                    if len(coords)>=2: lat, lon = float(coords[0]), float(coords[1])
                    c.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                             (nom, tel, lat, lon, nota, datetime.now()))
                    conn.commit()
                    st.session_state.radio_despacho = "Despacho"
                    st.rerun()
                else: st.error("Faltan datos")

    elif opcion == "Despacho":
        st.subheader("🚀 Despacho de Equipos")
        
        if st.button("⬅️ Volver a Registro"):
            reset_despacho()

        df_c = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
        df_l = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        df_r = pd.read_sql_query("SELECT usuario FROM usuarios WHERE rol='Repartidor'", conn)

        if not df_c.empty and not df_l.empty:
            # clear_on_submit asegura que tras el botón los widgets internos se vacíen
            with st.form("form_despacho_final", clear_on_submit=True):
                col1, col2 = st.columns(2)
                c_sel = col1.selectbox("👤 Cliente", df_c['nombre'])
                l_sel = col1.selectbox("🧺 Lavadora", df_l['serie'])
                rep_sel = col2.selectbox("🚚 Repartidor", df_r['usuario'])
                hrs = col2.number_input("Horas", min_value=1, value=4)
                confirmar = st.form_submit_button("🚀 Confirmar Salida")

            if confirmar:
                row_c = df_c[df_c['nombre'] == c_sel].iloc[0]
                id_l = df_l[df_l['serie'] == l_sel]['id'].values[0]
                
                c.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin, repartidor_asig) VALUES (?,?,?,?,?)",
                         (row_c['id'], id_l, datetime.now(), datetime.now() + timedelta(hours=hrs), rep_sel))
                c.execute("UPDATE lavadoras SET estado='En Camino' WHERE id=?", (id_l,))
                conn.commit()

                msg = f"✅ *¡Hola, {c_sel.upper()}!* \n\nTu lavadora ya salió. Repartidor: *{rep_sel.upper()}*."
                url_wa = f"https://wa.me/{row_c['tel']}?text={msg.replace(' ', '%20')}"
                
                st.success("¡Despacho registrado!")
                st.link_button("📲 Enviar WhatsApp", url_wa)
                
                # Botón de limpieza manual post-envío
                if st.button("Limpiar y Nuevo Despacho"):
                    st.rerun()
        else:
            st.warning("No hay equipos disponibles o clientes registrados.")

# --- OTROS MÓDULOS ---
elif menu == "🧺 Inventario Equipos":
    st.title("🧺 Gestión de Inventario")
    with st.form("inv", clear_on_submit=True):
        s = st.text_input("Serie")
        m = st.text_input("Modelo")
        if st.form_submit_button("Registrar"):
            c.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s,m))
            conn.commit()
            st.rerun()
    st.dataframe(pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn), use_container_width=True)

elif menu == "⏱️ Control de Tiempos":
    st.title("⏱️ Monitor de Alquileres")
    activos = pd.read_sql_query('''SELECT a.id, c.nombre, l.serie, a.fin FROM alquileres_activos a 
                                   JOIN clientes c ON a.id_cliente = c.id 
                                   JOIN lavadoras l ON a.id_lavadora = l.id''', conn)
    if activos.empty: st.info("Sin alquileres activos.")
    else: st.dataframe(activos, use_container_width=True)

elif menu == "📊 Reporte Admin":
    if rol_actual == "Admin":
        st.title("📊 Historial de Ventas")
        st.dataframe(pd.read_sql_query("SELECT * FROM historial_alquileres", conn), use_container_width=True)
    else: st.error("Acceso restringido.")
                
