# Arena Cup

MVP em Streamlit para inscrição individual de atletas, sorteio automático de equipes,
sorteio de confrontos e apostas com pontos virtuais.

## Executar

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Fluxo

1. Cada estudante se inscreve individualmente, informando nome, gênero e ano do curso.
2. As inscrições ficam abertas até 30/11/2026, data do torneio.
3. Na data definida, o app sorteia automaticamente 8 equipes com 7 ou 8 atletas,
   garantindo pelo menos duas mulheres em cada equipe e a presença mínima de dois homens.
4. Depois do sorteio das equipes, a organização sorteia a chave eliminatória simples
   de oito equipes: quartas, semifinais, terceiro lugar e final.
5. Apostadores identificam-se e usam um saldo inicial de 1.000 pontos virtuais.
6. Em **Painel administrativo**, entre com a senha configurada e lance os resultados.

O regulamento considera estudantes do 1º e 2º ano de Educação Física, partidas de
10 minutos corridos e desempate por tiros de 7 metros. A relação de atletas fica
bloqueada depois do sorteio para preservar a composição das equipes.

Os resultados administrativos liquidam as apostas e ficam no log de auditoria.

Antes de publicar, configure a variável de ambiente `ADMIN_PASSWORD` com uma senha
forte. O app não possui uma senha administrativa padrão: se essa variável não estiver
configurada, o painel administrativo permanecerá bloqueado.

> Este MVP é demonstrativo: não processa dinheiro real e não deve ser usado para ocultar
> manipulação de resultados. Qualquer correção de resultado deve ser justificada e auditada.
