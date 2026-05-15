import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
from contextlib import contextmanager

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v5.0", layout="wide", page_icon="🧺")

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

# --- ESTADOS DE SESIÓN (Control de Navegación) ---
if 'auth' not in st.session_state: 
    st.session_state['auth'] = False
if 'paso_idx' not in st.session_state:
    st.session_state.paso_idx = 0  # 0: Registro, 1: Despacho

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

# --- LÓGICA DE MÓDULOS ---

if menu == "🧺 Equipos":
    st.title("🧺 Gestión de Inventario")
    with st.form("reg_lav", clear_on_submit=True):
        col1, col2 = st.columns(2)
        s = col1.text_input("Número de Serie")
        m = col2.text_input("Modelo / Marca")
        if st.form_submit_button("Registrar Lavadora"):
            if s and m:
                with db_connection() as conn:
                    conn.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
                    conn.commit()
                st.success(f"Lavadora {s} registrada.")
            else: st.warning("Complete todos los campos.")
    
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
        st.dataframe(df, use_container_width=True)

elif menu == "👥 Clientes/Despacho":
    st.title("👥 Clientes y Salidas")
    
    # Selector de pestañas sincronizado con st.session_state.paso_idx
    paso = st.radio(
        "Acción:", 
        ["Registro", "Despacho"], 
        index=st.session_state.paso_idx, 
        horizontal=True,
        key="radio_navegacion" 
    )

    # Actualizamos el estado interno si el usuario hace click manualmente
    st.session_state.paso_idx = 0 if paso == "Registro" else 1

    # --- PESTAÑA REGISTRO ---
    if st.session_state.paso_idx == 0:
        with st.form("cli_form", clear_on_submit=True):
            st.subheader("📝 Nuevo Registro")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Ej: 573001234567)")
            gps = st.text_input("Link Ubicación")
            notas = st.text_area("Notas")
            
            if st.form_submit_button("Guardar y Continuar al Despacho"):
                if nom and tel:
                    coords = re.findall(r"([-+]?\d+\.\d+)", gps)
                    lat = float(coords[0]) if len(coords) >= 2 else 0.0
                    lon = float(coords[1]) if len(coords) >= 2 else 0.0
                    with db_connection() as conn:
                        conn.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                                     (nom, tel, lat, lon, notas, datetime.now()))
                        conn.commit()
                    
                    # AQUÍ ESTÁ EL TRUCO: Cambiamos el índice y recargamos
                    st.session_state.paso_idx = 1
                    st.rerun()
                else:
                    st.error("Nombre y Teléfono son obligatorios.")

    # --- PESTAÑA DESPACHO ---
    else:
        # BOTÓN PARA VOLVER A REGISTRO
        if st.button("⬅️ Volver a Nuevo Registro"):
            st.session_state.paso_idx = 0
            st.rerun()

        st.subheader("🚀 Nueva Salida de Equipo")
        with db_connection() as conn:
            clientes_df = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
            lavadoras_df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        
        if not clientes_df.empty and not lavadoras_df.empty:
            with st.form("despacho_form"):
                c_sel = st.selectbox("Seleccionar Cliente", clientes_df['nombre'])
                l_sel = st.selectbox("Seleccionar Lavadora", lavadoras_df['serie'])
                hrs = st.number_input("Horas de alquiler", 1, 72, 4)
                
                if st.form_submit_button("Confirmar Salida"):
                    # Extraer datos
                    c_data = clientes_df[clientes_df['nombre'] == c_sel].iloc[0]
                    id_c = c_data['id']
                    telefono = c_data['tel']
                    id_l = lavadoras_df[lavadoras_df['serie'] == l_sel]['id'].values[0]
                    f_fin = datetime.now() + timedelta(hours=hrs)
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin) VALUES (?,?,?,?)",
                                     (id_c, id_l, datetime.now(), f_fin))
                        conn.execute("UPDATE lavadoras SET estado='En Uso' WHERE id=?", (id_l,))
                        conn.commit()
                    
                    st.success(f"Salida registrada para {c_sel}")

                    # Botón WhatsApp
                    tel_limpio = "".join(filter(str.isdigit, str(telefono)))
                    msg = f"Hola {c_sel}, tu servicio inició. Equipo: {l_sel}. Vence: {f_fin.strftime('%H:%M')}."
                    wa_url = f"https://wa.me/{tel_limpio}?text={msg.replace(' ', '%20')}"
                    
                    st.markdown(f"""
                        <a href="{wa_url}" target="_blank" style="text-decoration: none;">
                            <div style="background-color: #25D366; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-top: 10px;">
                                Enviar Comprobante WhatsApp 📲
                            </div>
                        </a>
                    """, unsafe_allow_html=True)
        else:
            st.info("Asegúrese de tener clientes registrados y lavadoras 'Disponibles'.")

elif menu == "⏱️ Monitor":
    st.title("⏱️ Monitor en Tiempo Real")
    query = '''SELECT a.id, c.nombre, l.serie, l.id as lid, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    with db_connection() as conn:
        activos = pd.read_sql_query(query, conn)

    if activos.empty:
        st.info("No hay alquileres activos.")
    else:
        for _, row in activos.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([2,2,1])
                col1.write(f"**{row['nombre']}** ({row['serie']})")
                col2.write(f"Vence: {row['fin']}")
                if col3.button("Finalizar", key=f"fin_{row['id']}"):
                    with db_connection() as conn:
                        conn.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto, usuario_cobro) VALUES (?,?,?,?,?)",
                                     (row['id'], row['lid'], datetime.now(), 0.0, st.session_state['user']))
                        conn.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['lid'],))
                        conn.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                        conn.commit()
                    st.rerun()

elif menu == "🚚 Recepción":
    st.title("📥 Reingreso a Bodega")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    
    if df.empty:
        st.info("No hay equipos pendientes de reingreso.")
    
    for _, l in df.iterrows():
        if st.button(f"📥 Confirmar Bodega: {l['serie']}", key=f"rec_{l['id']}", use_container_width=True):
            with db_connection() as conn:
                conn.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
                conn.commit()
            st.rerun()

elif menu == "📊 Reportes":
    st.title("📊 Reportes de Historial")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    st.dataframe(df, use_container_width=True)

elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    if st.button("🔥 BORRAR TODA LA DATA", type="primary"):
        with db_connection() as conn:
            conn.execute("DELETE FROM alquileres_activos")
            conn.execute("DELETE FROM historial_alquileres")
            conn.execute("DELETE FROM lavadoras")
            conn.execute("DELETE FROM clientes")
            conn.commit()
        st.success("Sistema reseteado.")
        st.rerun()
                                             
