from app import db


class Color(db.Model):
	__tablename__ = "cores"

	id = db.Column(db.Integer, primary_key=True)

	# Nome interno da variável CSS, por exemplo: "cor-fundo", "cor-texto"
	nome_variavel = db.Column(db.String(50), nullable=False)

	# Valor padrão em formato HEX ou RGB, por exemplo: "#ffffff"
	valor_padrao = db.Column(db.String(50), nullable=False)

	# Valor atual aplicado (permite personalização sem perder o padrão)
	valor_atual = db.Column(db.String(20), nullable=True)

	# Descrição opcional para facilitar o entendimento no painel/admin
	descricao = db.Column(db.String(255), nullable=True)

	# Grupo/tema ao qual a variável pertence (root, rosa, azul, cinza, verde, preto)
	tema = db.Column(db.String(30), nullable=False, default="root")

	# Ambiente ao qual essa configuração de cor pertence
	# Deve corresponder ao campo enviroment em users.py para que
	# o tema seja aplicado apenas aos usuários daquele ambiente.
	enviroment = db.Column(db.String(100), nullable=False, index=True)

	def __repr__(self) -> str:  # pragma: no cover
		return f"<Color {self.nome_variavel} ({self.tema})>"
