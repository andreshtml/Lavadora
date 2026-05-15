import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
from contextlib import contextmanager

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v5.2", layout="wide", page_icon="🧺")

# --- GESTIÓN DE BASE DE DATOS ---
DB_NAME = 'sistema_lavanderia_v4.db'

@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
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
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, inicio DATETIME, fin DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_alquileres 
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, fecha DATETIME, 
                      monto REAL, usuario_cobro TEXT)''')
        c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera')")
        conn.commit()

inicializar_db()

# --- ESTADOS DE SESIÓN ---
if 'auth' not in st.session_state: 
    st.session_state['auth'] = False
if 'paso_idx' not in st.session_state:
    st.session_state.paso_idx = 0 

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

# --- NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👤 {st.session_state['user']}")
opciones_menu = ["🧺 Equipos", "👥 Clientes/Despacho", "⏱️ Monitor", "🚚 Recepción", "📊 Reportes"]
if st.session_state['rol'] == "Admin":
    opciones_menu.append("⚙️ Configuración")

menu = st.sidebar.selectbox("Menú Principal", opciones_menu)

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.clear()
    st.rerun()

# --- MÓDULO: CLIENTES Y DESPACHO ---
if menu == "👥 Clientes/Despacho":
    st.title("👥 Gestión de Clientes y Salidas")
    
    # Sincronización robusta: El radio button obedece al session_state
    opciones_pasos = ["Registro", "Despacho"]
    paso = st.radio(
        "Seleccione una acción:", 
        opciones_pasos, 
        index=st.session_state.paso_idx, 
        horizontal=True,
        key="nav_despacho"
    )

    # Actualizar el índice si el usuario hace clic manualmente en el radio
    st.session_state.paso_idx = opciones_pasos.index(paso)

    # --- PESTAÑA: REGISTRO (Índice 0) ---
    if st.session_state.paso_idx == 0:
        with st.form("cli_form", clear_on_submit=True):
            st.subheader("📝 Registrar Nuevo Cliente")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Ej: 573001234567)")
            gps = st.text_input("Link de Ubicación (Google Maps)")
            notas = st.text_area("Notas adicionales")
            
            if st.form_submit_button("✅ Guardar y Continuar al Despacho"):
                if nom and tel:
                    coords = re.findall(r"([-+]?\d+\.\d+)", gps)
                    lat = float(coords[0]) if len(coords) >= 2 else 0.0
                    lon = float(coords[1]) if len(coords) >= 2 else 0.0
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                                     (nom, tel, lat, lon, notas, datetime.now()))
                        conn.commit()
                    
                    # SALTO AUTOMÁTICO AL DESPACHO
                    st.session_state.paso_idx = 1
                    st.rerun()
                else:
                    st.error("Por favor rellene Nombre y Teléfono.")

    # --- PESTAÑA: DESPACHO (Índice 1) ---
    else:
        if st.button("⬅️ Volver a Nuevo Registro"):
            st.session_state.paso_idx = 0
            st.rerun()

        st.subheader("🚀 Nueva Salida de Equipo")
        with db_connection() as conn:
            # Traer clientes ordenados por ID descendente (el más reciente primero)
            clientes_df = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
            lavadoras_df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        
        if not clientes_df.empty and not lavadoras_df.empty:
            with st.form("despacho_form"):
                c_sel = st.selectbox("Cliente (Nuevo arriba)", clientes_df['nombre'])
                l_sel = st.selectbox("Lavadora Disponible", lavadoras_df['serie'])
                hrs = st.number_input("Horas de alquiler", 1, 72, 4)
                
                if st.form_submit_button("🚀 Confirmar Despacho"):
                    c_info = clientes_df[clientes_df['nombre'] == c_sel].iloc[0]
                    id_l = lavadoras_df[lavadoras_df['serie'] == l_sel]['id'].values[0]
                    f_fin = datetime.now() + timedelta(hours=hrs)
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin) VALUES (?,?,?,?)",
                                     (c_info['id'], id_l, datetime.now(), f_fin))
                        conn.execute("UPDATE lavadoras SET estado='En Uso' WHERE id=?", (id_l,))
                        conn.commit()
                    
                    st.success(f"¡Equipo {l_sel} entregado a {c_sel}!")
                    # El mensaje de WhatsApp ha sido eliminado de aquí.
                    # Puedes gestionar el contacto desde el Monitor si es necesario.
        else:
            st.warning("Asegúrate de tener clientes registrados y lavadoras disponibles.")

# --- MÓDULO: EQUIPOS ---
elif menu == "🧺 Equipos":
    st.title("🧺 Inventario de Equipos")
    with st.form("reg_lav", clear_on_submit=True):
        col1, col2 = st.columns(2)
        s = col1.text_input("Número de Serie")
        m = col2.text_input("Modelo")
        if st.form_submit_button("Registrar Lavadora"):
            with db_connection() as conn:
                conn.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
                conn.commit()
            st.success("Lavadora agregada.")
    
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
        st.dataframe(df, use_container_width=True)

# --- MÓDULO: MONITOR ---
elif menu == "⏱️ Monitor":
    st.title("⏱️ Monitor de Alquileres Activos")
    query = '''SELECT a.id, c.nombre, l.serie, l.id as lid, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    with db_connection() as conn:
        activos = pd.read_sql_query(query, conn)
    
    if activos.empty:
        st.info("No hay equipos en la calle actualmente.")
    else:
        for _, row in activos.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2,2,1])
                c1.write(f"👤 **{row['nombre']}**")
                c2.write(f"⏰ Fin programado: {row['fin']}")
                if c3.button("Finalizar", key=f"f_{row['id']}"):
                    with db_connection() as conn:
                        conn.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto) VALUES (?,?,?,0)", 
                                     (row['id'], row['lid'], datetime.now()))
                        conn.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['lid'],))
                        conn.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                        conn.commit()
                    st.rerun()

# --- MÓDULO: RECEPCIÓN ---
elif menu == "🚚 Recepción":
    st.title("📥 Reingreso a Bodega")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    
    if df.empty:
        st.info("No hay lavadoras pendientes de reingreso.")
    
    for _, l in df.iterrows():
        if st.button(f"📥 Confirmar Entrada: {l['serie']}", key=f"r_{l['id']}"):
            with db_connection() as conn:
                conn.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
                conn.commit()
            st.rerun()

# --- MÓDULO: REPORTES ---
elif menu == "📊 Reportes":
    st.title("📊 Historial de Servicios")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    st.dataframe(df, use_container_width=True)

# --- MÓDULO: CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Administración del Sistema")
    if st.button("🔥 Formatear Base de Datos", type="primary"):
        with db_connection() as conn:
            conn.execute("DELETE FROM alquileres_activos"); 
            conn.execute("DELETE FROM lavadoras");
            conn.execute("DELETE FROM clientes"); 
            conn.commit()
        st.success("Sistema reiniciado correctamente.")
        st.rerun()
                    
