# Recorta Mapas — orientações do projeto

Prepara camadas de territórios rurais para o Google My Maps a partir do Censo 2022 (IBGE).
Usado por irmãos da congregação, não só pelo autor: a tela principal precisa ser simples.

## Regras

1. **Português do Brasil** em tudo que o usuário vê (janela, mensagens, relatório, nomes de arquivo).
2. **Windows primeiro.** Sem arquivos `.bat`. O executável sai do GitHub Actions
   (`.github/workflows/windows.yml`) e é publicado em Releases a cada envio para `main`.
3. **Menos importações possível no My Maps.** O objetivo é abrir o mapa e importar o mínimo
   de arquivos. Os contornos dos territórios **não** entram nas pastas `Mapa_XX`: o usuário já
   tem uma camada própria com todos eles (`camada_territorios = "nao"`). Só casas e trajetos.
4. **Modelo de interface do Dicta** (outro projeto do autor):
   - **Desempenho antes de tudo na UX.** Nada visual que deixe algo mensuravelmente mais lento.
     Meça antes e depois (abertura da janela, troca de página) e ponha os números no commit.
   - **Escuro por padrão**, visual moderno de celular (cantos arredondados, chaves, chips), em
     ttk "clam" puro. Tema em `gui/tema.py` (copiado do Dicta, com cache em PNG das formas).
   - Barra lateral com páginas; botão Processar sempre visível no rodapé.
   - Mensagens dentro da janela (rodapé), nunca caixas de diálogo claras do sistema.
     Confirmações no próprio botão ("Clique de novo para…"). Só o seletor de arquivos é nativo.
   - Barra de título escura (`dark_title_bar`).
5. **Lembrar entre execuções** em `%APPDATA%\RecortaMapas` (fora da pasta do programa).
6. Leitura de CSV e processamento rodam em segundo plano; só a thread principal mexe no Tk
   (fila + `after`).
7. **Dependências** (`dependencias.py`): rodando do código, a janela confere na abertura se as
   bibliotecas existem (`find_spec`, ~0,3 ms) e instala sozinha o que falta, sem botão, com
   progresso no rodapé; as versões (metadados, ~15 ms) são conferidas em segundo plano depois que a
   janela aparece. A linha de comando faz o mesmo antes de processar. O .exe (`sys.frozen`) pula tudo.

## Números atuais (Linux, Xvfb)

- Abertura da janela com arquivos salvos: ~90–105 ms (1ª vez ~140 ms, desenha e grava o cache do tema).
- Troca de página: 2–9 ms (Casas ~35 ms quando precisa redesenhar após ler o CSV).

## Estrutura

`recorta_mapas/` (núcleo + `cli.py` + `gui/`), `tests/` (pytest, dados sintéticos),
`ferramentas/gerar_exemplo.py` (dados de exemplo do pacote), `recorta_mapas_gui.py` e
`recorta_mapas_app.py` (entradas do PyInstaller).

Testes: `pytest -q`.
