import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import time
from contextlib import contextmanager

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v5.0", layout="wide", page_icon="🧺")

# --- GESTIÓN ROBUSTA DE BASE DE DATOS ---
DB_NAME = 'sistema_lavanderia_v4.db'

@contextmanager
def db_connection():
    """Gestiona la conexión de forma segura para evitar bloqueos de hilos."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row # Permite acceder por nombre de columna
    try:
        yield conn
    finally:
        conn.close()

def inicializar_db():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, clave TEXT, rol TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS clientes 
                     (id INTEGER PRIMARY KEY, nombre TEXT, tel TEXT, lat REAL, lon REAL, notas TEXT, fecha_registro DATETIME)''')
        c.execute('CREATE TABLE IF NOT EXISTS lavadoras (id INTEGER PRIMARY KEY, serie TEXT, modelo TEXT, estado TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS alquileres_activos 
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, inicio DATETIME, fin DATETIME, 
                      repartidor_asig TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_alquileres 
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, fecha DATETIME, 
                      monto REAL, usuario_cobro TEXT)''')
        c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera')")
        conn.commit()

def registrar_log(accion):
    user = st.session_state.get('user', 'Sistema')
    with db_connection() as conn:
        conn.execute("INSERT INTO logs (usuario, accion, fecha) VALUES (?,?,?)", 
                     (user, accion, datetime.now()))
        conn.commit()

# Inicialización
inicializar_db()

# --- ESTADOS DE SESIÓN ---
if 'paso_despacho' not in st.session_state: st.session_state.paso_despacho = 0
if 'auth' not in st.session_state: st.session_state['auth'] = False

# --- AUTENTICACIÓN ---
if not st.session_state['auth']:
    st.title("🔐 Acceso Empresarial")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Iniciar Sesión"):
            with db_connection() as conn:
                res = conn.execute("SELECT rol FROM usuarios WHERE usuario=? AND clave=?", (u, p)).fetchone()
                if res:
                    st.session_state.update({'auth': True, 'user': u, 'rol': res['rol']})
                    st.rerun()
                else: st.error("Credenciales incorrectas")
    st.stop()

# --- NAVEGACIÓN ---
st.sidebar.title(f"👤 {st.session_state['user']}")
menu = st.sidebar.selectbox("Menú", ["🧺 Equipos", "👥 Clientes/Despacho", "⏱️ Monitor", "🚚 Recepción", "📊 Reportes"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO: INVENTARIO ---
if menu == "🧺 Equipos":
    st.title("🧺 Gestión de Inventario")
    with st.form("reg_lav", clear_on_submit=True):
        col1, col2 = st.columns(2)
        s = col1.text_input("Serie")
        m = col2.text_input("Modelo")
        if st.form_submit_button("Guardar"):
            if s and m:
                with db_connection() as conn:
                    conn.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
                    conn.commit()
                st.success("Registrada")
    
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
        st.table(df)

# --- MÓDULO: CLIENTES Y DESPACHO (CORREGIDO) ---
elif menu == "👥 Clientes/Despacho":
    opcion = st.radio("Acción:", ["Registro", "Despacho"], index=st.session_state.paso_despacho, horizontal=True)
    st.session_state.paso_despacho = 0 if opcion == "Registro" else 1

    if st.session_state.paso_despacho == 0:
        with st.form("cli_form", clear_on_submit=True):
            nom = st.text_input("Nombre")
            tel = st.text_input("WhatsApp")
            gps = st.text_input("Ubicación (Link)")
            if st.form_submit_button("Siguiente"):
                if nom and tel:
                    # Regex robusta para lat/lon en links de Google Maps
                    coords = re.findall(r"([-+]?\d+\.\d+)", gps)
                    lat = float(coords[0]) if len(coords) >= 2 else 0.0
                    lon = float(coords[1]) if len(coords) >= 2 else 0.0
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO clientes (nombre, tel, lat, lon, fecha_registro) VALUES (?,?,?,?,?)",
                                     (nom, tel, lat, lon, datetime.now()))
                        conn.commit()
                    st.session_state.paso_despacho = 1
                    st.rerun()

    else:
        st.subheader("🚀 Nueva Salida")
        with db_connection() as conn:
            clientes = pd.read_sql_query("SELECT id, nombre FROM clientes ORDER BY id DESC", conn)
            lavadoras = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        
        if not clientes.empty and not lavadoras.empty:
            with st.form("despacho_form"):
                c_sel = st.selectbox("Cliente", clientes['nombre'])
                l_sel = st.selectbox("Lavadora", lavadoras['serie'])
                hrs = st.number_input("Horas", 1, 48, 4)
                if st.form_submit_button("Despachar"):
                    id_c = clientes[clientes['nombre']==c_sel]['id'].values[0]
                    id_l = lavadoras[lavadoras['serie']==l_sel]['id'].values[0]
                    f_fin = datetime.now() + timedelta(hours=hrs)
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin) VALUES (?,?,?,?)",
                                     (id_c, id_l, datetime.now(), f_fin))
                        conn.execute("UPDATE lavadoras SET estado='En Uso' WHERE id=?", (id_l,))
                        conn.commit()
                    st.success("En camino")
                    st.rerun()
        else: st.warning("Faltan clientes o lavadoras disponibles.")

# --- MÓDULO: MONITOR (SOLUCIÓN ERROR DE COBRO) ---
elif menu == "⏱️ Monitor":
    st.title("⏱️ Control de Tiempos")
    query = '''SELECT a.id, c.nombre, l.serie, l.id as lid, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    
    with db_connection() as conn:
        activos = pd.read_sql_query(query, conn)

    for _, row in activos.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([2,2,1])
            col1.write(f"**{row['nombre']}** ({row['serie']})")
            
            # Manejo flexible de fechas con Pandas
            fin_dt = pd.to_datetime(row['fin'])
            resta = (fin_dt - datetime.now()).total_seconds() / 60
            col2.info(f"{int(resta)} min restantes") if resta > 0 else col2.error("TIEMPO VENCIDO")

            # Formulario único por fila para evitar pérdida de datos
            with col3.popover("🏁 Finalizar"):
                with st.form(f"f_{row['id']}"):
                    monto = st.number_input("Monto $", min_value=0.0, key=f"m_{row['id']}")
                    if st.form_submit_button("Cobrar"):
                        with db_connection() as conn:
                            conn.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto, usuario_cobro) VALUES (?,?,?,?,?)",
                                         (row['id'], row['lid'], datetime.now(), monto, st.session_state['user']))
                            conn.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['lid'],))
                            conn.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                            conn.commit()
                        st.rerun()

# --- MÓDULO: RECEPCIÓN ---
elif menu == "🚚 Recepción":
    st.title("📥 Reingreso a Bodega")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    
    for _, l in df.iterrows():
        if st.button(f"📥 Confirmar {l['serie']}", key=f"rec_{l['id']}"):
            with db_connection() as conn:
                conn.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
                conn.commit()
            st.rerun()

# --- MÓDULO: REPORTES ---
elif menu == "📊 Reportes":
    if st.session_state['rol'] != "Admin": st.error("No autorizado"); st.stop()
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    st.metric("Ventas Totales", f"${df['monto'].sum():,.2f}")
    st.dataframe(df, use_container_width=True)
            
