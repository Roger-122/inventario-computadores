from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import winrm

app = Flask(__name__)

BANCO = "inventario.db"

# ============================================================
# CONFIGURAÇÃO DO COMPUTADOR REMOTO
# ============================================================

USUARIO = "ti"
SENHA = "tsfiles"


# ============================================================
# CONEXÃO COM O BANCO
# ============================================================

def conectar_banco():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao


# ============================================================
# CRIAÇÃO DO BANCO
# ============================================================

def criar_banco():

    conexao = conectar_banco()

    conexao.execute("""
        CREATE TABLE IF NOT EXISTS computadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            ip TEXT NOT NULL UNIQUE,
            sistema TEXT,
            status TEXT,
            so_versao TEXT,
            memoria_ram_gb TEXT,
            processador TEXT,
            disco_c_gb TEXT
        )
    """)
    conexao.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_computadores_ip ON computadores(ip)
    """)
    conexao.commit()

    # --------------------------------------------------------
    # Caso o banco antigo já exista, adiciona as novas colunas
    # --------------------------------------------------------

    colunas = conexao.execute(
        "PRAGMA table_info(computadores)"
    ).fetchall()

    nomes_colunas = [coluna["name"] for coluna in colunas]

    novas_colunas = {
        "so_versao": "TEXT",
        "memoria_ram_gb": "TEXT",
        "processador": "TEXT",
        "disco_c_gb": "TEXT"
    }

    for coluna, tipo in novas_colunas.items():

        if coluna not in nomes_colunas:

            conexao.execute(
                f"ALTER TABLE computadores ADD COLUMN {coluna} {tipo}"
            )

    conexao.commit()
    conexao.close()


# ============================================================
# COLETA AS INFORMAÇÕES DO COMPUTADOR WINDOWS
# ============================================================

def coletar_informacoes(ip):

    print()
    print("========================================")
    print("Tentando coletar dados do IP:", ip)
    print("========================================")

    try:

        # ----------------------------------------------------
        # Conecta no computador Windows usando WinRM
        # ----------------------------------------------------

        sessao = winrm.Session(
            f"http://{ip}:5985/wsman",
            auth=(usuario, senha),
            transport="ntlm"
        )

        # ----------------------------------------------------
        # Comando PowerShell
        # ----------------------------------------------------

        comando = r"""
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$disco = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"

[PSCustomObject]@{
    Nome = $cs.Name
    Sistema = "Windows"
    VersaoSO = $os.Caption + " " + $os.Version
    MemoriaRAM = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
    Processador = $cpu.Name
    DiscoC = [math]::Round($disco.Size / 1GB, 2)
} | ConvertTo-Json -Compress
"""

        resultado = sessao.run_ps(comando)

        # ----------------------------------------------------
        # Verifica se o comando funcionou
        # ----------------------------------------------------

        if resultado.status_code != 0:

            erro = resultado.std_err.decode(
                "utf-8",
                errors="ignore"
            )

            print("ERRO NO WINDOWS:")
            print(erro)

            return None

        # ----------------------------------------------------
        # Lê o resultado
        # ----------------------------------------------------

        import json

        texto = resultado.std_out.decode(
            "utf-8",
            errors="ignore"
        ).strip()

        print("Resposta recebida:")
        print(texto)

        dados = json.loads(texto)

        # ----------------------------------------------------
        # Monta os dados da máquina
        # ----------------------------------------------------

        dados_maquina = {

            "IP": ip,

            "Sistema": dados.get(
                "Sistema",
                "Windows"
            ),

            "Nome_Maquina": dados.get(
                "Nome",
                "Desconhecido"
            ),

            "Memoria_RAM_GB": dados.get(
                "MemoriaRAM",
                ""
            ),

            "SO_versao": dados.get(
                "VersaoSO",
                ""
            ),

            "Processador": dados.get(
                "Processador",
                ""
            ),

            "Disco_C_GB": dados.get(
                "DiscoC",
                ""
            )
        }

        print()
        print("DADOS COLETADOS:")
        print("------------------------------")
        print("Nome:", dados_maquina["Nome_Maquina"])
        print("IP:", dados_maquina["IP"])
        print("Sistema:", dados_maquina["Sistema"])
        print("Versão:", dados_maquina["SO_versao"])
        print("RAM:", dados_maquina["Memoria_RAM_GB"], "GB")
        print("Processador:", dados_maquina["Processador"])
        print("Disco C:", dados_maquina["Disco_C_GB"], "GB")
        print("------------------------------")

        return dados_maquina

    except Exception as erro:

        print()
        print("ERRO AO CONECTAR NO COMPUTADOR:")
        print(erro)

        return None


# ============================================================
# SALVAR NO BANCO
# ============================================================

def salvar_no_banco(dados):

    conexao = conectar_banco()

    conexao.execute("""
        INSERT INTO computadores
        (
            nome,
            ip,
            sistema,
            status,
            so_versao,
            memoria_ram_gb,
            processador,
            disco_c_gb
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(ip) DO UPDATE SET

            nome = excluded.nome,
            sistema = excluded.sistema,
            status = excluded.status,
            so_versao = excluded.so_versao,
            memoria_ram_gb = excluded.memoria_ram_gb,
            processador = excluded.processador,
            disco_c_gb = excluded.disco_c_gb
    """, (

        dados["Nome_Maquina"],
        dados["IP"],
        dados["Sistema"],
        "Ativo",
        dados["SO_versao"],
        dados["Memoria_RAM_GB"],
        dados["Processador"],
        dados["Disco_C_GB"]
    ))

    conexao.commit()
    conexao.close()

    print()
    print("Dados salvos no banco com sucesso!")


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():

    # --------------------------------------------------------
    # Quando o usuário digitar um IP
    # --------------------------------------------------------

    if request.method == "POST":

        ip_digitado = request.form.get("ip", "").strip()

        if ip_digitado:

            print()
            print("IP informado:", ip_digitado)

            # ------------------------------------------------
            # Tenta coletar as informações
            # ------------------------------------------------

            dados = coletar_informacoes(ip_digitado)

            # ------------------------------------------------
            # Se conseguiu coletar
            # ------------------------------------------------

            if dados:

                salvar_no_banco(dados)

            else:

                print()
                print("Não foi possível coletar os dados.")
                print("Verifique IP, usuário, senha e WinRM.")

            return redirect(
                url_for("index")
            )

    # --------------------------------------------------------
    # Busca todos os computadores cadastrados
    # --------------------------------------------------------

    conexao = conectar_banco()

    lista = conexao.execute("""
        SELECT *
        FROM computadores
        ORDER BY id DESC
    """).fetchall()

    conexao.close()

    return render_template(
        "index.html",
        computadores=lista
    )
# ============================================================
# EXCLUIR COMPUTADOR
# ============================================================

@app.route("/excluir/<ip>", methods=["POST"])
def excluir_computador(ip):

    conexao = conectar_banco()

    conexao.execute(
        "DELETE FROM computadores WHERE ip = ?",
        (ip,)
    )

    conexao.commit()
    conexao.close()

    return redirect(url_for("index"))

# ============================================================
# INICIAR PROGRAMA
# ============================================================

if __name__ == "__main__":

    criar_banco()

    print("========================================")
    print("Servidor iniciado!")
    print("========================================")
    print("Acesse no navegador:")
    print("http://127.0.0.1:5000")
    print("========================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )