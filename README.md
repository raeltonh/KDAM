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
- carregar um `.ksf` Atlas Max como template,
- converter em lote,
- baixar um `.zip` com os arquivos convertidos,
- exibir recomendacoes operacionais com base no conteudo do `.ksf`,
- avisar quando a origem indicar `Black T'shirt` e recomendar `Black setup` na Atlas Max.

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
