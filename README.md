# KSF Converter

Conversor e app local para reescrever arquivos `.ksf` antigos no formato Atlas Max Plus usando um `.ksf` Atlas como template.

## App local com Streamlit

```bash
pip install -r requirements.txt
streamlit run app.py
```

Depois abra:

```text
http://localhost:8501
```

O app permite:

- carregar um ou varios `.ksf` de origem,
- carregar um ou mais `.zip` de origem,
- ler `.ksf` recursivamente dentro de ZIP,
- carregar um `.ksf` Atlas Max como template,
- converter em lote,
- gerar relatorio por arquivo,
- baixar um `.zip` com os arquivos convertidos,
- baixar os `.ksf` convertidos individualmente,
- exibir recomendacoes operacionais com base no conteudo do `.ksf`,
- avisar quando a origem indicar `Black T'shirt` e recomendar `Black setup` na Atlas Max.
- publicar alteracoes locais no GitHub pelo painel `GitHub sync`, desde que a autenticacao git local ja esteja configurada.

## Atualizar GitHub pelo app

O painel `GitHub sync` fica no sidebar do Streamlit. Ele mostra a branch atual, o remoto `origin`, quantos commits locais ainda nao foram enviados e se existem arquivos modificados.

Para publicar:

1. confirme a mensagem de commit,
2. marque `Include new untracked files` somente se quiser incluir arquivos novos,
3. clique em `Commit and push to GitHub`.

Se o app mostrar erro de autenticacao, configure o acesso ao GitHub no computador primeiro. O app usa o proprio `git push` local e nao salva token ou senha.

## Modos de entrada e entrega

Entrada:

- `Arquivo individual`: upload manual de um ou varios `.ksf`
- `ZIP`: upload de um ou mais `.zip` com busca recursiva por `.ksf`
- `Misto`: combinacao dos dois modos

Entrega:

- `ZIP`: empacota os arquivos convertidos preservando a estrutura relativa e inclui `conversion-report.json`
- `Individual files`: gera cada `.ksf` convertido separadamente no app, com download individual e relatorio JSON separado

## Regra fixa do app

O app foi simplificado para usar somente o fluxo que funciona:

- geometria: sempre usa a do template Atlas Max,
- copias: sempre usa a do template Atlas Max,
- nome interno do setup: usa o nome do arquivo convertido,
- offsets X/Y: ficam em zero por padrao.

## Como funciona

- O template Atlas fornece os campos dependentes da maquina e do setup.
- O arquivo de origem preserva os dados variaveis do job.
- A geometria pode ser preservada do arquivo original ou substituida pela do template.
- Ajustes finos de `XOffsetMM` e `YOffsetMM` podem ser aplicados via linha de comando.

## Uso

```bash
python3 convert_ksf.py \
  "/caminho/origem.ksf" \
  "/caminho/template-atlas.ksf" \
  "/caminho/saida.ksf"
```

Exemplo em lote:

```bash
python3 convert_ksf.py \
  "/caminho/pasta-vulcan" \
  "/caminho/template-atlas.ksf" \
  "/caminho/pasta-saida"
```

## Opcoes uteis

- `--geometry-mode source|template`
- `--copies-mode source|template`
- `--set-name-mode template|source-file`
- `--x-offset-delta 4`
- `--y-offset-delta -10`
- `--suffix "_converted"`

## Observacao

O conversor foi preparado para o fluxo descrito na reuniao: aplicar setup Atlas, manter dados do job e permitir compensacao opcional de coordenadas.
