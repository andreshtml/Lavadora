Import streamlit as st
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
    """Gestiona la conexión de forma segura."""
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

# --- NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👤 {st.session_state['user']}")
opciones_menu = ["🧺 Equipos", "👥 Clientes/Despacho", "⏱️ Monitor", "🚚 Recepción", "📊 Reportes"]
if st.session_state['rol'] == "Admin":
    opciones_menu.append("⚙️ Configuración")

menu = st.sidebar.selectbox("Menú Principal", opciones_menu)

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO 0: INVENTARIO ---
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

# --- MÓDULO 1: CLIENTES Y DESPACHO ---
elif menu == "👥 Clientes/Despacho":
    st.title("👥 Clientes y Salidas")
    opcion = st.radio("Acción:", ["Registro", "Despacho"], index=st.session_state.paso_despacho, horizontal=True)
    st.session_state.paso_despacho = 0 if opcion == "Registro" else 1

    if st.session_state.paso_despacho == 0:
        with st.form("cli_form", clear_on_submit=True):
            st.subheader("📝 Nuevo Registro")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Incluir código de país)")
            gps = st.text_input("Link Ubicación")
            notas = st.text_area("Notas")
            if st.form_submit_button("Guardar y Continuar"):
                if nom and tel:
                    coords = re.findall(r"([-+]?\d+\.\d+)", gps)
                    lat = float(coords[0]) if len(coords) >= 2 else 0.0
                    lon = float(coords[1]) if len(coords) >= 2 else 0.0
                    with db_connection() as conn:
                        conn.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                                     (nom, tel, lat, lon, notas, datetime.now()))
                        conn.commit()
                    st.session_state.paso_despacho = 1
                    st.rerun()
                else: st.error("Nombre y Teléfono requeridos.")

    else:
        st.subheader("🚀 Nueva Salida de Equipo")
        with db_connection() as conn:
            clientes_df = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
            lavadoras_df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        
        if not clientes_df.empty and not lavadoras_df.empty:
            with st.form("despacho_form"):
                c_sel = st.selectbox("Cliente", clientes_df['nombre'])
                l_sel = st.selectbox("Lavadora", lavadoras_df['serie'])
                hrs = st.number_input("Horas de alquiler", 1, 72, 4)
                
                if st.form_submit_button("Confirmar Salida"):
                    # Obtener datos para el registro y el mensaje
                    cliente_info = clientes_df[clientes_df['nombre'] == c_sel].iloc[0]
                    id_c = cliente_info['id']
                    telefono = cliente_info['tel']
                    id_l = lavadoras_df[lavadoras_df['serie'] == l_sel]['id'].values[0]
                    f_fin = datetime.now() + timedelta(hours=hrs)
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin) VALUES (?,?,?,?)",
                                     (id_c, id_l, datetime.now(), f_fin))
                        conn.execute("UPDATE lavadoras SET estado='En Uso' WHERE id=?", (id_l,))
                        conn.commit()
                    
                    st.success(f"Salida de {l_sel} registrada con éxito.")

                    # --- LÓGICA DEL BOTÓN DIRECTO A WHATSAPP ---
                    # Limpiamos el teléfono (solo números)
                    tel_limpio = "".join(filter(str.isdigit, str(telefono)))
                    texto_msg = f"Hola {c_sel}, su servicio de lavandería ha iniciado. Equipo: {l_sel}. Entrega: {f_fin.strftime('%H:%M')}."
                    wa_url = f"https://wa.me/{tel_limpio}?text={texto_msg.replace(' ', '%20')}"
                    
                    # El botón aparece inmediatamente después de confirmar
                    st.markdown(f"""
                        <a href="{wa_url}" target="_blank" style="text-decoration: none;">
                            <div style="
                                background-color: #25D366;
                                color: white;
                                padding: 15px;
                                border-radius: 10px;
                                text-align: center;
                                font-weight: bold;
                                font-size: 18px;
                                cursor: pointer;
                                border: 1px solid #128C7E;
                                margin-top: 20px;">
                                Enviar WhatsApp a {c_sel} 📲
                            </div>
                        </a>
                    """, unsafe_allow_html=True)

        elif clientes_df.empty:
            st.warning("No hay clientes registrados.")
        else:
            st.warning("No hay equipos disponibles.")

# --- MÓDULO 2: MONITOR ---
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
                col2.write(f"Fin: {row['fin']}")
                if col3.button("Finalizar", key=f"btn_{row['id']}"):
                    with db_connection() as conn:
                        conn.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto, usuario_cobro) VALUES (?,?,?,?,?)",
                                     (row['id'], row['lid'], datetime.now(), 0.0, st.session_state['user']))
                        conn.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['lid'],))
                        conn.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                        conn.commit()
                    st.rerun()

# --- MÓDULO 3: RECEPCIÓN ---
elif menu == "🚚 Recepción":
    st.title("📥 Reingreso a Bodega")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    for _, l in df.iterrows():
        if st.button(f"📥 Bodega: {l['serie']}", key=f"rec_{l['id']}", use_container_width=True):
            with db_connection() as conn:
                conn.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
                conn.commit()
            st.rerun()

# --- MÓDULO 4: REPORTES ---
elif menu == "📊 Reportes":
    st.title("📊 Reportes de Historial")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    st.dataframe(df, use_container_width=True)

# --- MÓDULO 5: CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración de Sistema")
    with st.container(border=True):
        st.warning("Zona de Peligro: Borrado de Base de Datos")
        if st.button("🔥 EJECUTAR BORRADO TOTAL", type="primary"):
            with db_connection() as conn:
                conn.execute("DELETE FROM alquileres_activos")
                conn.execute("DELETE FROM historial_alquileres")
                conn.execute("DELETE FROM lavadoras")
                conn.execute("DELETE FROM clientes")
                conn.commit()
                st.success("Base de datos vaciada.")
                st.rerun()
