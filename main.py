import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import webbrowser

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

# --- FUNCIONES DE AYUDA ---
def abrir_whatsapp(telefono, mensaje):
    """Genera un link de WhatsApp y usa componentes de Streamlit para abrirlo"""
    msg_encoded = mensaje.replace(' ', '%20').replace('\n', '%0A')
    url_wa = f"https://wa.me/{telefono}?text={msg_encoded}"
    # JS para abrir en pestaña nueva automáticamente
    st.components.v1.html(f"""
        <script type="text/javascript">
            window.open('{url_wa}', '_blank');
        </script>
    """, height=0)

# --- ESTADO DE NAVEGACIÓN ---
if 'paso_despacho' not in st.session_state:
    st.session_state.paso_despacho = "Registro"

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
            conn.commit()
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
    with st.form("reg_lavadora", clear_on_submit=True):
        col1, col2 = st.columns(2)
        s = col1.text_input("Número de Serie")
        m = col2.text_input("Modelo / Marca")
        if st.form_submit_button("Registrar Lavadora"):
            if s and m:
                c.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
                conn.commit()
                st.success(f"Lavadora {s} registrada")
    
    df_lavs = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
    st.dataframe(df_lavs, use_container_width=True)

# --- MÓDULO 1: CLIENTES Y DESPACHO ---
elif menu == "👥 Clientes y Despacho":
    st.title("👥 Gestión de Clientes y Salida")

    opcion = st.radio("Seleccione Acción:", ["Registro", "Despacho"], 
                      index=0 if st.session_state.paso_despacho == "Registro" else 1,
                      horizontal=True)

    if opcion == "Registro":
        with st.form("reg_cli", clear_on_submit=True):
            st.subheader("➕ Registro Nuevo Cliente")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Ej: 58412...)")
            gps = st.text_input("Link Ubicación WhatsApp")
            nota = st.text_area("Notas de Dirección")
            if st.form_submit_button("Guardar Cliente y Continuar"):
                if nom and tel:
                    lat, lon = 0.0, 0.0
                    coords = re.findall(r"([-+]?\d*\.\d+|\d+)", gps)
                    if len(coords)>=2: lat, lon = float(coords[0]), float(coords[1])
                    c.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                             (nom, tel, lat, lon, nota, datetime.now()))
                    conn.commit()
                    st.session_state.paso_despacho = "Despacho"
                    st.rerun()
                else: st.error("Nombre y Teléfono requeridos")

    else:
        st.subheader("🚀 Despacho de Equipos")
        if st.button("⬅️ Volver a Registro"):
            st.session_state.paso_despacho = "Registro"
            st.rerun()

        df_c = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
        df_l = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        df_r = pd.read_sql_query("SELECT usuario FROM usuarios WHERE rol='Repartidor'", conn)

        if not df_c.empty and not df_l.empty:
            c1, c2 = st.columns(2)
            c_sel = c1.selectbox("👤 Seleccionar Cliente", df_c['nombre'])
            l_sel = c1.selectbox("🧺 Seleccionar Lavadora", df_l['serie'])
            rep_sel = c2.selectbox("🚚 Asignar Repartidor", df_r['usuario'])
            hrs = c2.number_input("Horas de Alquiler", min_value=1, value=4)

            if st.button("🚀 Confirmar Salida y Enviar WhatsApp"):
                # Obtener datos del cliente seleccionado
                row_c = df_c[df_c['nombre'] == c_sel].iloc[0]
                id_l = df_l[df_l['serie'] == l_sel]['id'].values[0]
                f_ini = datetime.now()
                f_fin = f_ini + timedelta(hours=int(hrs))

                # Guardar en DB
                c.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin, repartidor_asig) VALUES (?,?,?,?,?)",
                         (int(row_c['id']), int(id_l), f_ini, f_fin, rep_sel))
                c.execute("UPDATE lavadoras SET estado='En Camino' WHERE id=?", (int(id_l),))
                conn.commit()

                # Mensaje automático
                mensaje = f"✅ *¡HOLA {c_sel.upper()}!*\n\nTu pedido de lavadora ha sido procesado.\n🚚 *Repartidor:* {rep_sel}\n⏱️ *Tiempo:* {hrs} horas.\n\n*Gracias por preferir Lavandería Master Pro.*"
                
                # Ejecutar apertura automática
                abrir_whatsapp(row_c['tel'], mensaje)
                
                st.success(f"Despacho registrado. Se ha intentado abrir WhatsApp para {row_c['tel']}")
                st.session_state.paso_despacho = "Registro"
                time.sleep(2)
                st.rerun()
        else:
            st.warning("Asegúrese de tener clientes registrados y lavadoras disponibles.")

# --- MÓDULO 2: CONTROL Y COBRO ---
elif menu == "⏱️ Control de Tiempos":
    st.title("⏱️ Monitor de Alquileres")
    query = '''SELECT a.id, c.nombre, c.tel, l.serie, l.id as id_lav, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    activos = pd.read_sql_query(query, conn)

    for _, row in activos.iterrows():
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            col1.write(f"**Cliente:** {row['nombre']} | **Equipo:** {row['serie']}")
            if col2.button("🏁 Finalizar/Cobrar", key=f"btn_{row['id']}"):
                c.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['id_lav'],))
                c.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                conn.commit()
                st.rerun()

# --- OTROS MÓDULOS (REPORTES / LOGÍSTICA) ---
# Se mantienen igual para no alargar el código...
