# Arena Cup

MVP em Streamlit para inscrição individual de atletas, sorteio automático de equipes,
sorteio de confrontos e apostas com pontos virtuais.

## Executar

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Fluxo

1. Cada estudante cria um cadastro básico individual, informando nome, gênero e ano do curso.
2. As inscrições ficam abertas até **27/11/2026 às 12:30**.
3. Às **15:30 de 27/11/2026**, o app sorteia automaticamente 8 equipes com 7 ou 8 atletas,
   garantindo pelo menos duas mulheres em cada equipe e a presença mínima de dois homens.
   O capitão de cada equipe também é escolhido aleatoriamente entre seus integrantes.
4. O mesmo sorteio cria automaticamente a chave eliminatória simples de oito equipes:
   quartas, semifinais, terceiro lugar e final.
5. Apostadores identificam-se e usam um saldo inicial de 1.000 pontos virtuais.
6. Em **Painel administrativo**, entre com a senha configurada e lance os resultados.

Antes do sorteio, somente o administrador visualiza a relação completa de inscritos.
Após o sorteio, a tela principal exibe as equipes formadas, seus integrantes e os
confrontos; cada competidor também vê em destaque a equipe em que caiu.
Os cadastros e o resultado do sorteio são mantidos em SQLite para serem compartilhados
entre as sessões dos participantes. O caminho pode ser alterado pela variável
`ARENA_DATABASE_PATH`.

A interface usa uma identidade visual de competição de handebol, com painel do torneio,
cards das equipes, capitão em destaque, indicadores de atletas/confrontos e confrontos
organizados em uma chave visual.

O regulamento considera estudantes do 1º e 2º ano de Educação Física, partidas de
10 minutos corridos e desempate por tiros de 7 metros. A relação de atletas fica
bloqueada depois do sorteio para preservar a composição das equipes.

Os resultados administrativos liquidam as apostas e ficam no log de auditoria.

Antes de publicar, configure a variável de ambiente `ADMIN_PASSWORD` com uma senha
forte. O app não possui uma senha administrativa padrão: se essa variável não estiver
configurada, o painel administrativo permanecerá bloqueado.

> Este MVP é demonstrativo: não processa dinheiro real e não deve ser usado para ocultar
> manipulação de resultados. Qualquer correção de resultado deve ser justificada e auditada.
