import streamlit as st
import psycopg2
import os
import pandas as pd
import streamlit.components.v1 as components
from dotenv import load_dotenv
from datetime import date
import bcrypt   # <--- Importante

load_dotenv()
st.set_page_config(page_title="Brider ERP Mobile", page_icon="🔋", layout="centered")

# --- ESTILOS (ligeros) ---
st.markdown("""
    <style>
        html, body, [class*="css"] { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        .stButton>button { border-radius: 8px !important; padding: 0.6rem 1rem !important; font-weight: 600 !important; }
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background-color: rgba(0,0,0,0.6);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            backdrop-filter: blur(4px);
            padding: 1rem;
        }
        .modal-box {
            background-color: white;
            border-radius: 16px;
            padding: 2rem 2.5rem;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            animation: fadeIn 0.3s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        .modal-box h3 { margin-top: 0; color: #1e293b; font-weight: 700; }
        .modal-box p { color: #475569; margin: 1rem 0 1.5rem 0; font-size: 1.1rem; }
        .modal-box .stButton button { min-width: 100px; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = None
if 'nombre_completo' not in st.session_state:
    st.session_state.nombre_completo = None
if 'rol_actual' not in st.session_state:
    st.session_state.rol_actual = None
if 'carrito' not in st.session_state:
    st.session_state.carrito = []
if 'id_venta_generado' not in st.session_state:
    st.session_state.id_venta_generado = None
if 'ultima_venta' not in st.session_state:
    st.session_state.ultima_venta = None
if 'mostrar_modal' not in st.session_state:
    st.session_state.mostrar_modal = False
if 'fecha_venta' not in st.session_state:
    st.session_state.fecha_venta = date.today()
if 'cliente_seleccionado' not in st.session_state:
    st.session_state.cliente_seleccionado = None
if 'tipo_pago' not in st.session_state:
    st.session_state.tipo_pago = "Contado"
if 'monto_contado' not in st.session_state:
    st.session_state.monto_contado = 0.0
if 'monto_credito' not in st.session_state:
    st.session_state.monto_credito = 0.0
if 'medio_cash' not in st.session_state:
    st.session_state.medio_cash = "Ninguno"
if 'total_factura' not in st.session_state:
    st.session_state.total_factura = 0.0

# --- FUNCIONES DE BASE DE DATOS (con caché) ---
@st.cache_resource
def init_connection():
    try:
        db_url = st.secrets["DATABASE_URL"]
    except Exception:
        db_url = os.getenv("DATABASE_URL")
    return psycopg2.connect(db_url, sslmode="require")

@st.cache_data(ttl=300)
def obtener_clientes():
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ruc, razon_social FROM clientes ORDER BY razon_social;")
    filas = cursor.fetchall()
    cursor.close()
    return [f"{fila[0]} | {fila[1]}" for fila in filas]

@st.cache_data(ttl=300)
def obtener_catalogo_completo():
    conn = init_connection()
    cursor = conn.cursor()
    # Adaptado a la nueva estructura con descripcion y precio_con_igv
    cursor.execute("SELECT id_bateria, modelo, descripcion, precio_con_igv, stock_actual FROM catalogo_baterias;")
    filas = cursor.fetchall()
    cursor.close()
    return filas

def verificar_login(user, password):
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, nombre_apellido, rol FROM usuarios WHERE username = %s;", (user,))
    resultado = cursor.fetchone()
    cursor.close()
    if not resultado:
        return None
    hash_almacenado = resultado[0]
    # Validar que el hash tenga formato bcrypt
    if not hash_almacenado or not isinstance(hash_almacenado, str) or not hash_almacenado.startswith('$2'):
        return None
    try:
        if bcrypt.checkpw(password.encode('utf-8'), hash_almacenado.encode('utf-8')):
            return {"nombre": resultado[1], "rol": resultado[2]}
    except ValueError:
        return None
    return None

def guardar_bateria_nueva(codigo, modelo, descripcion, piezas, aplicacion, precio_lista, precio_con_igv, stock):
    conn = init_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO catalogo_baterias 
            (codigo, modelo, descripcion, piezas_por_caja, aplicacion, precio_lista, precio_con_igv, stock_actual)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (codigo, modelo, descripcion, piezas, aplicacion, precio_lista, precio_con_igv, stock))
        conn.commit()
        st.cache_data.clear()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cursor.close()

def registrar_venta_corporativa_multi(ruc, fecha, tipo_pago, total_general, m_contado, m_credito, vendedor, medio_cash, carrito):
    conn = init_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO ventas_cabecera (
                ruc_cliente, fecha_venta, tipo_pago, monto_total, 
                vendedor, estado_auditoria, monto_contado, monto_credito, medio_pago_cash
            )
            VALUES (%s, %s, %s, %s, %s, 'Pendiente', %s, %s, %s) RETURNING id_venta;
        """, (ruc, fecha, tipo_pago, total_general, vendedor, m_contado, m_credito, medio_cash))
        id_venta = cursor.fetchone()[0]

        for item in carrito:
            # Nota: precio_unitario_sin_igv se puede calcular, aquí lo ponemos como 0 o se obtiene del catálogo
            cursor.execute("""
                INSERT INTO ventas_detalle (id_venta, id_bateria, cantidad, descuento_porcentaje, 
                                            precio_unitario_sin_igv, subtotal, igv, total_pagar)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (id_venta, item["id"], item["cantidad"], item["desc_pct"], 
                  0.0, item["subtotal"], item["igv"], item["total"]))

            # **El trigger se encarga de actualizar el stock, así que no hacemos UPDATE aquí**

        conn.commit()
        st.cache_data.clear()
        return id_venta
    except Exception as e:
        conn.rollback()
        st.error(f"Error crítico en transacción: {e}")
        return None
    finally:
        cursor.close()

# =========================================================================
# LOGIN
# =========================================================================
if not st.session_state.autenticado:
    st.markdown("<h3 style='text-align: center; font-weight: 700;'>🔋 GRUPO BRIDER</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Gestión Comercial Móvil</p>", unsafe_allow_html=True)
    with st.form("login_mobile"):
        input_user = st.text_input("Usuario")
        input_pass = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar al Sistema", use_container_width=True):
            user_data = verificar_login(input_user.strip(), input_pass.strip())
            if user_data:
                st.session_state.autenticado = True
                st.session_state.usuario_actual = input_user
                st.session_state.nombre_completo = user_data["nombre"]
                st.session_state.rol_actual = user_data["rol"]
                st.rerun()
            else:
                st.error("Credenciales de acceso inválidas")
    st.stop()

# =========================================================================
# MODAL DE CONFIRMACIÓN (si está activo)
# =========================================================================
if st.session_state.mostrar_modal:
    # Ocultar contenido principal y mostrar solo el modal
    st.markdown("""
        <div class="modal-overlay">
            <div class="modal-box">
                <h3>⚠️ Confirmar venta</h3>
                <p>Estás a punto de registrar una venta por <strong>S/. {:.2f}</strong>.<br>¿Deseas continuar?</p>
    """.format(st.session_state.total_factura), unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar", use_container_width=True, key="confirm_btn"):
            with st.spinner("Registrando venta..."):
                ruc_cliente = st.session_state.cliente_seleccionado.split(" | ")[0]
                id_gen = registrar_venta_corporativa_multi(
                    ruc_cliente,
                    st.session_state.fecha_venta,
                    st.session_state.tipo_pago,
                    st.session_state.total_factura,
                    st.session_state.monto_contado,
                    st.session_state.monto_credito,
                    st.session_state.nombre_completo,
                    st.session_state.medio_cash,
                    st.session_state.carrito
                )
                if id_gen:
                    st.session_state.ultima_venta = {
                        "id": id_gen,
                        "cliente": st.session_state.cliente_seleccionado.split(" | ")[1],
                        "tipo_pago": st.session_state.tipo_pago,
                        "monto_contado": st.session_state.monto_contado,
                        "monto_credito": st.session_state.monto_credito,
                        "medio_pago_cash": st.session_state.medio_cash,
                        "total": st.session_state.total_factura
                    }
                    st.session_state.carrito = []
                    st.session_state.id_venta_generado = id_gen
                    st.session_state.mostrar_modal = False
                    st.toast("✅ Venta registrada exitosamente", icon="🎉")
                    st.rerun()
                else:
                    st.error("Error al registrar la venta. Intenta nuevamente.")
                    st.session_state.mostrar_modal = False
                    st.rerun()
    with col2:
        if st.button("❌ Cancelar", use_container_width=True, key="cancel_btn"):
            st.session_state.mostrar_modal = False
            st.rerun()
    
    st.markdown("</div></div>", unsafe_allow_html=True)
    st.stop()  # Detener para que no se vea el contenido principal

# =========================================================================
# CONTENIDO PRINCIPAL (solo si no hay modal)
# =========================================================================
st.markdown(f"<p style='text-align: right; font-size: 0.85rem; color: #666;'>👤 {st.session_state.nombre_completo} ({st.session_state.rol_actual})</p>", unsafe_allow_html=True)
st.title("🛒 Terminal de Ventas")

# Obtener datos
lista_clientes = obtener_clientes()
datos_catalogo = obtener_catalogo_completo()

# Construir opciones y diccionario para el selectbox
opciones_baterias = [f"{d[1]} - S/.{d[3]} (Stock: {d[4]})" for d in datos_catalogo]
diccionario_baterias = {f"{d[1]} - S/.{d[3]} (Stock: {d[4]})": {"id": d[0], "modelo": d[1], "precio": d[3], "stock": d[4]} for d in datos_catalogo}

# --- PANEL ADMIN (adaptado) ---
if st.session_state.rol_actual == "Administrador":
    with st.expander("🛠️ Panel Admin: Añadir Batería al Catálogo"):
        with st.form("add_bateria"):
            n_codigo = st.text_input("Código (Ej: BBR00001)")
            n_modelo = st.text_input("Modelo (Ej: 12N5-3B)")
            n_descripcion = st.text_area("Descripción completa")
            n_piezas = st.number_input("Piezas por caja", min_value=1, step=1, value=1)
            n_aplicacion = st.text_area("Aplicación (vehículos compatibles)")
            n_precio_lista = st.number_input("Precio lista (sin IGV)", min_value=0.0, format="%.2f")
            n_precio_con_igv = st.number_input("Precio con IGV", min_value=0.0, format="%.2f")
            n_stock = st.number_input("Stock inicial", min_value=0, step=1)
            if st.form_submit_button("Guardar en Catálogo"):
                if n_codigo and n_modelo and guardar_bateria_nueva(n_codigo, n_modelo, n_descripcion, n_piezas, n_aplicacion, n_precio_lista, n_precio_con_igv, n_stock):
                    st.toast("✅ Batería agregada exitosamente", icon="🎉")
                    st.rerun()
                else:
                    st.error("Error al registrar producto. Verifica que todos los campos estén llenos.")

# --- CLIENTE ---
cliente_sel = st.selectbox("1. Seleccione el Cliente", lista_clientes)
st.session_state.cliente_seleccionado = cliente_sel
st.markdown("---")

# --- CARRITO ---
st.subheader("2. Añadir Baterías")
if not opciones_baterias:
    st.warning("No hay baterías en el catálogo. Contacte al administrador.")
    st.stop()

bateria_sel = st.selectbox("Modelo de Batería", opciones_baterias)
bat_info = diccionario_baterias[bateria_sel]

cant_input = st.number_input("Cantidad", min_value=1, step=1, value=1)
desc_input = st.selectbox("Descuento Aplicable", ["10%", "15%", "20%", "0%"], index=0)

# Verificar stock disponible (considerando lo ya agregado al carrito)
cant_en_carrito = sum(item["cantidad"] for item in st.session_state.carrito if item["id"] == bat_info["id"])
stock_real_disponible = bat_info["stock"] - cant_en_carrito

if st.button("🛒 Añadir al Carrito", use_container_width=True):
    if cant_input > stock_real_disponible:
        st.error(f"Stock insuficiente. Disponible neto en almacén: {stock_real_disponible} unidades.")
    else:
        p_unitario = float(bat_info["precio"])
        pct = float(desc_input.replace("%", "")) / 100
        t_bruto = p_unitario * cant_input
        t_desc = t_bruto * pct
        t_pagar_item = t_bruto - t_desc
        sub_item = t_pagar_item / 1.18
        igv_item = t_pagar_item - sub_item
        
        st.session_state.carrito.append({
            "id": bat_info["id"],
            "modelo": bat_info["modelo"],
            "cantidad": cant_input,
            "desc_pct": pct * 100,
            "subtotal": sub_item,
            "igv": igv_item,
            "total": t_pagar_item
        })
        st.toast(f"✅ {bat_info['modelo']} añadido al carrito", icon="🛒")
        st.rerun()

# --- DETALLE DEL CARRITO ---
if st.session_state.carrito:
    st.markdown("### **Detalle del Carrito**")
    df_carrito = pd.DataFrame(st.session_state.carrito)
    st.dataframe(df_carrito[["modelo", "cantidad", "total"]], hide_index=True, use_container_width=True)
    
    if st.button("🗑️ Vaciar Carrito", type="secondary"):
        st.session_state.carrito = []
        st.rerun()
        
    st.markdown("---")

    # --- PARÁMETROS DE PAGO Y FECHA ---
    st.subheader("3. Parámetros de Pago")
    total_factura = sum(item["total"] for item in st.session_state.carrito)
    st.metric(label="TOTAL GENERAL A COBRAR", value=f"S/. {total_factura:.2f}")

    # Fecha
    fecha_venta = st.date_input("Fecha de la venta", value=st.session_state.fecha_venta)
    st.session_state.fecha_venta = fecha_venta

    tipo_pago = st.selectbox("Método de Pago", ["Contado", "Crédito", "Mixto"])
    st.session_state.tipo_pago = tipo_pago
    st.session_state.total_factura = total_factura

    monto_contado = 0.0
    monto_credito = 0.0
    medio_cash_sel = "Ninguno"

    if tipo_pago == "Contado":
        monto_contado = total_factura
        medio_cash_sel = st.selectbox("Canal de Recepción Cash", ["Efectivo", "Yape", "Plin", "Visa", "Mastercard", "Transferencia"])
    elif tipo_pago == "Crédito":
        monto_credito = total_factura
    elif tipo_pago == "Mixto":
        monto_contado = st.number_input("Monto pagado al Contado (S/.)", min_value=0.0, max_value=float(total_factura), step=10.0)
        monto_credito = float(total_factura) - monto_contado
        st.warning(f"Saldo restante a Crédito: S/. {monto_credito:.2f}")
        if monto_contado > 0:
            medio_cash_sel = st.selectbox("Canal de Recepción Cash (Parte Líquida)", ["Efectivo", "Yape", "Plin", "Visa", "Mastercard", "Transferencia"])

    st.session_state.monto_contado = monto_contado
    st.session_state.monto_credito = monto_credito
    st.session_state.medio_cash = medio_cash_sel

    st.markdown("---")

    # --- BOTÓN REGISTRAR VENTA ---
    if st.button("🚀 Registrar Venta", type="primary", use_container_width=True):
        st.session_state.mostrar_modal = True
        st.rerun()

# --- VOUCHER EMITIDO ---
if st.session_state.id_venta_generado is not None and st.session_state.ultima_venta:
    v = st.session_state.ultima_venta
    st.success("🎉 ¡Operación Registrada Exitosamente!")
    
    ticket_movil = f"""*BRIDER E.I.R.L. - COMPROBANTE*
----------------------------------------
*Doc Nro:* TR-{v['id']:05d}
*Fecha:* {st.session_state.fecha_venta.strftime('%d/%m/%Y')}
*Vendedor:* {st.session_state.nombre_completo}
*Cliente:* {v['cliente']}
----------------------------------------
*Condición:* {v['tipo_pago']}
*Canal Cash:* {v['medio_pago_cash']}
*Cobrado Cash:* S/. {v['monto_contado']:.2f}
*Por Cobrar:* S/. {v['monto_credito']:.2f}
----------------------------------------
*TOTAL PROCESADO: S/. {v['total']:.2f}*
----------------------------------------
¡Gracias por confiar en Grupo Brider!
"""
    st.code(ticket_movil, language="text")
    ticket_js = ticket_movil.replace("\n", "\\n")
    
    html_share = f"""
    <button id="nativeShareBtn" style="
        width: 100%;
        background-color: #1E293B;
        color: white;
        border: none;
        padding: 12px 20px;
        font-size: 16px;
        font-weight: 600;
        border-radius: 8px;
        cursor: pointer;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    ">
        🔗 Compartir Comprobante
    </button>
    <script>
        const btn = document.getElementById('nativeShareBtn');
        btn.addEventListener('click', async () => {{
            const shareData = {{
                title: 'Comprobante Brider',
                text: `{ticket_js}`
            }};
            try {{
                if (navigator.share) {{
                    await navigator.share(shareData);
                }} else {{
                    navigator.clipboard.writeText(shareData.text);
                    alert('Texto de la factura copiado al portapapeles.');
                }}
            }} catch (err) {{
                console.log('Cancelado:', err);
            }}
        }});
    </script>
    """
    components.html(html_share, height=55)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Nueva Transacción 🔁", use_container_width=True):
        st.session_state.id_venta_generado = None
        st.session_state.ultima_venta = None
        st.rerun()

# --- CIERRE DE SESIÓN ---
st.markdown("<br><br>", unsafe_allow_html=True)
if st.button("🔒 Cerrar Sesión del Sistema", type="secondary", use_container_width=True):
    for key in ['autenticado', 'usuario_actual', 'nombre_completo', 'rol_actual', 'carrito', 
                'id_venta_generado', 'ultima_venta', 'mostrar_modal']:
        if key in st.session_state:
            st.session_state[key] = None if key == 'usuario_actual' else False if key in ['autenticado','mostrar_modal'] else []
    st.rerun()
