import streamlit as st
import psycopg2
import numpy as np
import pandas as pd
import itertools
import uuid
import io
import zipfile

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(
    page_title="Encuesta AHP – Café Arábigo",
    layout="wide"
)

# =====================================================
# AHP – CONSISTENCY RATIO (NO TOCAR)
# =====================================================
RI = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49
}

def calculate_cr(matrix):
    matrix = np.array(matrix)
    n = matrix.shape[0]
    eigvals, _ = np.linalg.eig(matrix)
    lambda_max = max(eigvals.real)
    CI = (lambda_max - n) / (n - 1)
    CR = CI / RI[n] if n in RI else 0
    return round(CR, 4)

# =====================================================
# DATABASE – SUPABASE / POSTGRESQL
# =====================================================
@st.cache_resource
def get_db():
    return psycopg2.connect(
        host=st.secrets["database"]["host"],
        dbname=st.secrets["database"]["dbname"],
        user=st.secrets["database"]["user"],
        password=st.secrets["database"]["password"],
        port=st.secrets["database"]["port"],
        sslmode="require"
    )

def init_db():
    with get_db() as con:
        cur = con.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS criteria (
            project_id UUID REFERENCES projects(id),
            name TEXT NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id UUID PRIMARY KEY,
            project_id UUID REFERENCES projects(id),
            user_name TEXT,
            cr NUMERIC
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS matrices (
            response_id UUID REFERENCES responses(id),
            i INTEGER,
            j INTEGER,
            value NUMERIC
        )
        """)

        con.commit()

#     evitar que se ejecute infinitamente
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

# =====================================================
# ROUTING
# =====================================================
project_id = st.query_params.get("project_id")

# =====================================================
# ===================== ADMIN =========================
# =====================================================
if project_id is None:

    st.title("Administrador – Encuestas AHP")

    project_name = st.text_input("Nombre del Proyecto")
    n_criteria = st.number_input("Número de Criterios", 2, 20, 2)

    criteria = [
        st.text_input(f"Criterio {i+1}")
        for i in range(int(n_criteria))
    ]

    if st.button("Crear Proyecto"):
        if not project_name or not all(criteria):
            st.error("Complete todos los campos")
            st.stop()

        pid = uuid.uuid4()

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO projects (id, name) VALUES (%s, %s)",
                (pid, project_name)
            )
            for c in criteria:
                cur.execute(
                    "INSERT INTO criteria (project_id, name) VALUES (%s, %s)",
                    (pid, c)
                )
            con.commit()

        APP_URL = "https://app-encuesta-ahp.streamlit.app"
        st.success("PROYECTO CREADO CORRECTAMENTE")
        st.code(f"{APP_URL}/?project_id={pid}")
        st.info("Este enlace es el que debe enviar a los encuestados")

    st.divider()
    st.subheader("📥 DESCARGAR RESULTADOS")

    with get_db() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM projects")
        projects = cur.fetchall()

    if not projects:
        st.info("No hay proyectos creados aún")
        st.stop()

    project_map = {name: pid for pid, name in projects}
    selected_project = st.selectbox("Proyecto", list(project_map.keys()))
    selected_pid = project_map[selected_project]

    with get_db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, user_name, cr FROM responses WHERE project_id=%s",
            (selected_pid,)
        )
        responses = cur.fetchall()

        cur.execute(
            "SELECT name FROM criteria WHERE project_id=%s",
            (selected_pid,)
        )
        criteria = [c[0] for c in cur.fetchall()]

    if not responses:
        st.warning("Este proyecto no tiene respuestas")
        st.stop()

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for rid, user, cr in responses:
            with get_db() as con:
                cur = con.cursor()
                cur.execute(
                    "SELECT i, j, value FROM matrices WHERE response_id=%s",
                    (rid,)
                )
                data = cur.fetchall()

            size = len(criteria)
            matrix = np.ones((size, size))
            for i, j, v in data:
                matrix[i][j] = v

            df_m = pd.DataFrame(matrix, index=criteria, columns=criteria)
            df_c = pd.DataFrame({"CR": [cr]})

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_m.to_excel(writer, sheet_name="Matriz_AHP")
                df_c.to_excel(writer, sheet_name="Consistencia", index=False)

            zipf.writestr(f"{user}.xlsx", buf.getvalue())

    st.download_button(
        "⬇️ Descargar TODAS las matrices (ZIP)",
        data=zip_buffer.getvalue(),
        file_name=f"Resultados_{selected_project}.zip"
    )

# =====================================================
# ================== ENCUESTADO =======================
# =====================================================
else:
    st.title("""CONSULTA A EXPERTOS MEDIANTE ENCUESTA CON MÉTODO AHP:
    Identificación de zonas óptimas para el cultivo de café arábigo en la cuenca hidrográfica del río La Paila, 
    mediante la integración de análisis geoespacial y evaluación multicriterio""")

    with get_db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM criteria WHERE project_id=%s",
            (project_id,)
        )
        criteria = [c[0] for c in cur.fetchall()]
        
    if not criteria:
        st.error("Este proyecto no existe o fue eliminado")
        st.stop()

         st.markdown("""
    El **Proceso Analítico Jerárquico (AHP)** es un método multicriterio ampliamente utilizado para la toma de decisiones complejas, 
    permitiendo comparar variables de forma estructurada y consistente. El AHP permite asignar pesos relativos a diferentes criterios 
    a partir del juicio experto, transformando valoraciones cualitativas en resultados cuantitativos confiables. 
    
    El objetivo de esta encuesta es determinar el grado de influencia relativa de diversos factores climatológicos, topográficos, edáficos y socioeconómicos
    sobre el desarrollo y la aptitud del café arábigo, con el fin de establecer ponderaciones técnicas que respalden análisis territoriales y evaluaciones de idoneidad.
    
    Hemos seleccionado su participación como experto en café para que pueda aportar su conocimiento 
    y experiencia en la valoración de los criterios que influyen en el desarrollo del café arábigo.
    La información recolectada será utilizada exclusivamente con fines académicos, sin ningún uso comercial distinto al ámbito investigativo.
    
    **Instrucciones ➜**
    La evaluación se realiza mediante comparaciones por pares. En cada fila se presentan dos criterios, usted debe: 
    
    **1.** Seleccionar cuál criterio es más importante 
    
    **2.** Indicar la intensidad de preferencia (escala 1–9 de Saaty) 
    
    **ESCALA AHP** 
    
    ● 1 = Igual importancia (el criterio A es igual de importante al criterio B)
    
    ● 3 = Moderada importancia (la experiencia y el juicio favorecen LIGERAMENTE al criterio A sobre el B)
    
    ● 5 = Fuerte importancia (la experiencia y el juicio favorecen FUERTEMENTE al criterio A sobre el B)
    
    ● 7 = Muy fuerte importancia (el criterio A es mucho más importante que el B)
    
    ● 9 = Extrema importancia (la mayor importancia del criterio A sobre el B está fuera de toda duda)
    
    ● Los valores pares (2,4,6,8) representan intensidades intermedias
    
    Tener en cuenta que un CR menor a **0.10** indica consistencia aceptable.
    """)


    user_name = st.text_input("INGRESE SU NOMBRE")

    pairs = list(itertools.combinations(range(len(criteria)), 2))
    matrix = np.ones((len(criteria), len(criteria)))

    st.subheader("Comparaciones por pares")

    for i, j in pairs:
        c1, c2, _ = st.columns([4, 4, 3])

        with c1:
            choice = st.selectbox(
                f"{criteria[i]} vs {criteria[j]}",
                ["", criteria[i], criteria[j]],
                key=f"c_{i}_{j}"
            )

        with c2:
            value = st.selectbox(
                "Intensidad",
                ["", 1, 2, 3, 4, 5, 6, 7, 8, 9],
                key=f"v_{i}_{j}"
            )

        if choice and value:
            if choice == criteria[i]:
                matrix[i][j] = value
                matrix[j][i] = 1 / value
            else:
                matrix[j][i] = value
                matrix[i][j] = 1 / value

    if st.button("Enviar encuesta"):
        if not user_name:
            st.error("Ingrese su nombre")
            st.stop()

        cr = calculate_cr(matrix)
        response_id = uuid.uuid4()

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO responses (id, project_id, user_name, cr) VALUES (%s,%s,%s,%s)",
                (response_id, project_id, user_name, cr)
            )

            for i in range(len(criteria)):
                for j in range(len(criteria)):
                    cur.execute(
                        "INSERT INTO matrices VALUES (%s,%s,%s,%s)",
                        (response_id, i, j, float(matrix[i][j]))
                    )

            con.commit()

        st.success("Encuesta enviada correctamente, gracias por su contribución")
        st.metric("Consistency Ratio (CR)", cr)

        df_m = pd.DataFrame(matrix, index=criteria, columns=criteria)
        df_c = pd.DataFrame({"CR": [cr]})

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_m.to_excel(writer, sheet_name="Matriz_AHP")
            df_c.to_excel(writer, sheet_name="Consistencia", index=False)

        st.download_button(
            "Descargar su matriz AHP",
            data=buffer.getvalue(),
            file_name=f"MatrizAHP_{user_name}.xlsx"
        )
