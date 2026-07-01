import streamlit as st
import psycopg2
import os
import pandas as pd
import streamlit.components.v1 as components  # <--- Agrega esto arriba si no lo tienes
import urllib.parse  # Herramienta nativa para codificar texto para la web
from dotenv import load_dotenv
from datetime import date

load_dotenv()
st.set_page_config(page_title="Brider ERP Mobile", page_icon="🔋", layout="centered")

# --- INYECCIÓN DE ESTILO SERIO e INNOVADOR (CSS CUSTOM) ---
st.markdown("""
    <style>
        /* Tipografía limpia y ejecutiva */
        html, body, [class*="css"] {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }
        /* Botones principales más corporativos */
        .stButton>button {
            border-radius: 8px !important;
            padding: 0.6rem 1rem !important;
            font-weight: 600 !important;
        }
        /* Tarjetas de datos limpias */
        div[data-testid="stBlock"] {
            border-radius: 10px;
        }
        /* Ocultar barra superior innecesaria en móvil */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN DE MEMORIA DE SESIÓN ---
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
if 'venta_preparada' not in st.session_state:
    st.session_state.venta_preparada = False
if 'id_venta_generado' not in st.session_state:
    st.session_state.id_venta_generado = None

@st.cache_resource
def init_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

conn = init_connection()

# --- FUNCIONES BASE DE DATOS ---
def verificar_login(user, password):
    cursor = conn.cursor()
    cursor.execute("SELECT nombre_apellido, rol FROM usuarios WHERE username = %s AND password_plana = %s;", (user, password))
    resultado = cursor.fetchone()
    return {"nombre": resultado[0], "rol": resultado[1]} if resultado else None

def obtener_clientes():
    cursor = conn.cursor()
    cursor.execute("SELECT ruc, razon_social FROM clientes ORDER BY razon_social;")
    return [f"{fila[0]} | {fila[1]}" for fila in cursor.fetchall()]

def obtener_catalogo_completo():
    cursor = conn.cursor()
    cursor.execute("SELECT id_bateria, modelo, tipo, precio_con_igv, stock_actual FROM catalogo_baterias;")
    return cursor.fetchall()

def registrar_venta_corporativa_multi(ruc, fecha, tipo_pago, total_general, m_contado, m_credito, vendedor, carrito):
    cursor = conn.cursor()
    try:
        # 1. Insertar Cabecera con desglose de pagos
        cursor.execute("""
            INSERT INTO ventas_cabecera (ruc_cliente, fecha_venta, tipo_pago, monto_total, vendedor, estado_auditoria, monto_contado, monto_credito)
            VALUES (%s, %s, %s, %s, %s, 'Pendiente', %s, %s) RETURNING id_venta;
        """, (ruc, fecha, tipo_pago, total_general, vendedor, m_contado, m_credito))
        id_venta = cursor.fetchone()[0]

        # 2. Insertar múltiples ítems del carrito y actualizar stocks individuales
        for item in carrito:
            cursor.execute("""
                INSERT INTO ventas_detalle (id_venta, id_bateria, cantidad, descuento_porcentaje, subtotal, igv, total_pagar)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (id_venta, item["id"], item["cantidad"], item["desc_pct"], item["subtotal"], item["igv"], item["total"]))

            cursor.execute("UPDATE catalogo_baterias SET stock_actual = stock_actual - %s WHERE id_bateria = %s;", (item["cantidad"], item["id"]))

        conn.commit()
        return id_venta
    except Exception as e:
        conn.rollback()
        st.error(f"Error crítico en transacción: {e}")
        return None

# =========================================================================
# CONTROL DE ACCESO (LOGIN)
# =========================================================================

if 'ultima_venta' not in st.session_state:
    st.session_state.ultima_venta = None

if not st.session_state.autenticado:
    st.markdown("<h3 style='text-align: center; font-weight: 700;'>🔋 GRUPO BRIDER</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Gestión Comercial Móvil</p>", unsafe_allow_html=True)
    
    with st.form("login_mobile"):
        input_user = st.text_input("Usuario")
        input_pass = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar", use_container_width=True):
            user_data = verificar_login(input_user.strip(), input_pass.strip())
            if user_data:
                st.session_state.autenticado = True
                st.session_state.usuario_actual = input_user
                st.session_state.nombre_completo = user_data["nombre"]
                st.session_state.rol_actual = user_data["rol"]
                st.rerun()
            else:
                st.error("Credenciales inválidas")
    st.stop()

# =========================================================================
# APLICACIÓN PRINCIPAL (DISEÑO ESTRICTAMENTE VERTICAL FOR SMARTPHONES)
# =========================================================================

# Indicador de usuario superior discreto y serio
st.markdown(f"<p style='text-align: right; font-size: 0.85rem; color: #666;'>👤 {st.session_state.nombre_completo} ({st.session_state.rol_actual})</p>", unsafe_allow_html=True)

st.title("🛒 Nueva Venta")

lista_clientes = obtener_clientes()
datos_catalogo = obtener_catalogo_completo()

opciones_baterias = [f"{d[1]} - S/.{d[3]} (Stock: {d[4]})" for d in datos_catalogo]
diccionario_baterias = {f"{d[1]} - S/.{d[3]} (Stock: {d[4]})": {"id": d[0], "modelo": d[1], "precio": d[3], "stock": d[4]} for d in datos_catalogo}

# --- SECCIÓN 1: SELECCIÓN DEL CLIENTE ---
cliente_sel = st.selectbox("1. Seleccione el Cliente", lista_clientes)

st.markdown("---")

# --- SECCIÓN 2: AGREGADOR DE PRODUCTOS (CARRITO) ---
st.subheader("2. Añadir Baterías")
bateria_sel = st.selectbox("Modelo de Batería", opciones_baterias)
bat_info = diccionario_baterias[bateria_sel]

cant_input = st.number_input("Cantidad", min_value=1, step=1, value=1)
desc_input = st.selectbox("Descuento Aplicable", ["10%", "15%", "20%", "0%"], index=0)

# Verificar si el producto ya está en el carrito para calcular stock real disponible
cant_en_carrito = sum(item["cantidad"] for item in st.session_state.carrito if item["id"] == bat_info["id"])
stock_real_disponible = bat_info["stock"] - cant_en_carrito

if st.button("🛒 Añadir al Carrito", use_container_width=True):
    if cant_input > stock_real_disponible:
        st.error(f"Falta stock. Disponible neto: {stock_real_disponible} unidades.")
    else:
        # Matemática de la línea de producto
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
        st.success(f"{bat_info['modelo']} añadido.")
        st.rerun()

# --- SECCIÓN 3: VISUALIZACIÓN DEL CARRITO ---
if st.session_state.carrito:
    st.markdown("### **Detalle del Carrito**")
    df_carrito = pd.DataFrame(st.session_state.carrito)
    # Mostramos una tabla simplificada y limpia para el celular
    st.dataframe(df_carrito[["modelo", "cantidad", "total"]], hide_index=True, use_container_width=True)
    
    if st.button("🗑️ Vaciar Carrito", type="secondary"):
        st.session_state.carrito = []
        st.session_state.venta_preparada = False
        st.rerun()
        
    st.markdown("---")

    # --- SECCIÓN 4: LOGÍSTICA DE PAGO TOTAL ---
    st.subheader("3. Parámetros de Pago")
    total_factura = sum(item["total"] for item in st.session_state.carrito)
    st.metric(label="TOTAL GENERAL A COBRAR", value=f"S/. {total_factura:.2f}")

    tipo_pago = st.selectbox("Método de Pago", ["Contado", "Crédito", "Mixto"])
    
    monto_contado = 0.0
    monto_credito = 0.0
    
    if tipo_pago == "Contado":
        monto_contado = total_factura
    elif tipo_pago == "Crédito":
        monto_credito = total_factura
    elif tipo_pago == "Mixto":
        monto_contado = st.number_input("Monto pagado al Contado (S/.)", min_value=0.0, max_value=float(total_factura), step=10.0)
        monto_credito = float(total_factura) - monto_contado
        st.warning(f"Saldo restante a Crédito: S/. {monto_credito:.2f}")

    st.markdown("---")

    # --- SECCIÓN 5: PROCESAMIENTO CON DOBLE CONFIRMACIÓN ---
    if not st.session_state.venta_preparada and st.session_state.id_venta_generado is None:
        if st.button("🚀 Procesar Venta", type="primary", use_container_width=True):
            st.session_state.venta_preparada = True
            st.rerun()

    if st.session_state.venta_preparada:
        st.warning(f"**¿Confirmar registro de venta?** Total: S/. {total_factura:.2f}")
        if st.button("Confirmar y Registrar ✅", use_container_width=True):
            ruc_cliente = cliente_sel.split(" | ")[0]
            
            id_gen = registrar_venta_corporativa_multi(
                ruc_cliente, date.today(), tipo_pago, total_factura,
                monto_contado, monto_credito, st.session_state.nombre_completo, st.session_state.carrito
            )
            
            if id_gen:
                # Guardamos la data del ticket en la memoria persistente
                st.session_state.ultima_venta = {
                    "id": id_gen,
                    "cliente": cliente_sel.split(" | ")[1],
                    "tipo_pago": tipo_pago,
                    "monto_contado": monto_contado,
                    "monto_credito": monto_credito,
                    "total": total_factura
                }
                
                st.session_state.carrito = [] # Ahora sí podemos limpiar el carrito tranquilos
                st.session_state.venta_preparada = False
                st.session_state.id_venta_generado = id_gen
                st.rerun()
        
        if st.button("Modificar / Volver atrás", use_container_width=True):
            st.session_state.venta_preparada = False
            st.rerun()

# --- SECCIÓN 6: VOUCHER MÓVIL CON MENÚ DE COMPARTIR NATIVO ---
if st.session_state.id_venta_generado is not None and st.session_state.ultima_venta:
    v = st.session_state.ultima_venta
    st.success("🎉 ¡Operación Registrada!")
    
    # 1. Formateamos el texto del ticket (con asteriscos para que salga en negrita si eligen WhatsApp)
    ticket_movil = f"""*BRIDER E.I.R.L. - COMPROBANTE*
----------------------------------------
*Doc Nro:* TR-{v['id']:05d}
*Fecha:* {date.today()}
*Vendedor:* {st.session_state.nombre_completo}
*Cliente:* {v['cliente']}
----------------------------------------
*Condición:* {v['tipo_pago']}
*Cobrado Cash:* S/. {v['monto_contado']:.2f}
*Por Cobrar:* S/. {v['monto_credito']:.2f}
----------------------------------------
*TOTAL PROCESADO: S/. {v['total']:.2f}*
----------------------------------------
¡Gracias por su compra!
"""
    
    # Mostramos el voucher en pantalla
    st.code(ticket_movil, language="text")
    
    # Escapamos los saltos de línea para que el JavaScript no rompa las comillas
    ticket_js = ticket_movil.replace("\n", "\\n")
    
    # 2. Inyectamos un botón nativo ultra innovador con JavaScript
    html_share_button = f"""
    <button id="nativeShareBtn" style="
        width: 100%;
        background-color: #1E293B; /* Color pizarra oscuro, ultra corporativo y serio */
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
                    // Despierta la hoja de compartir nativa de Android o iOS
                    await navigator.share(shareData);
                }} else {{
                    // Fallback por si lo prueban en una PC de escritorio antigua
                    navigator.clipboard.writeText(shareData.text);
                    alert('Texto copiado al portapapeles de forma segura.');
                }}
            }} catch (err) {{
                console.log('El usuario canceló o hubo un error:', err);
            }}
        }});
    </script>
    """
    
    # Renderizamos el botón dentro de la app móvil con una altura fija para que no genere scrollbar
    components.html(html_share_button, height=55)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Nueva Transacción 🔁", use_container_width=True):
        st.session_state.id_venta_generado = None
        st.session_state.ultima_venta = None
        st.rerun()

# --- BOTÓN DISCRETO PARA CERRAR SESIÓN ---
st.markdown("<br><br>", unsafe_allow_html=True)
if st.button("Cerrar Sesión", type="secondary", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()