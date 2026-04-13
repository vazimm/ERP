from app import db
from sqlalchemy import CheckConstraint

# Capacidade máxima global do estoque (número máximo de itens somados entre todas as categorias).
# Cada ambiente pode ter sua própria capacidade lógica (250, 500, 750 ou 1000),
# armazenada na coluna `capacity` da tabela. A constraint abaixo apenas garante
# que nunca ultrapassaremos o limite físico global (1000).
#
# IMPORTANTE: se alterar este valor, também atualize o literal da CheckConstraint
# e aplique a migração/recriação da tabela conforme o seu fluxo de banco de dados.
DEFAULT_CAPACITY = 1000


class Estoque(db.Model):
    __tablename__ = 'estoque'

    id = db.Column(db.Integer, primary_key=True)
    p45 = db.Column(db.Integer, nullable=False, default=0)
    p20 = db.Column(db.Integer, nullable=False, default=0)
    p13 = db.Column(db.Integer, nullable=False, default=0)
    p8 = db.Column(db.Integer, nullable=False, default=0)
    p5 = db.Column(db.Integer, nullable=False, default=0)
    agua = db.Column(db.Integer, nullable=False, default=0)
    enviroment = db.Column(db.String(100), nullable=False, index=True)
    # Capacidade lógica máxima para este ambiente (250, 500, 750, 1000, ...).
    capacity = db.Column(db.Integer, nullable=False, default=DEFAULT_CAPACITY)

    # Constraint de banco que garante que a soma de todos os campos do estoque
    # não ultrapasse a capacidade máxima global (atualmente 1000).
    # Nota: a expressão da constraint precisa ser alterada manualmente se modificar
    # DEFAULT_CAPACITY (veja comentário acima).
    __table_args__ = (
        CheckConstraint('p45 + p20 + p13 + p8 + p5 + agua <= 1000', name='ck_estoque_total_max'),
    )

    def total(self):
        """Retorna a soma de todos os itens do estoque."""
        return int((self.p45 or 0) + (self.p20 or 0) + (self.p13 or 0) + (self.p8 or 0) + (self.p5 or 0) + (self.agua or 0))

    def percent(self, capacity: int | None = None):
        """Retorna o percentual ocupado do estoque (arredondado).

        Se nenhuma capacidade for informada, usa a capacidade do próprio
        registro (self.capacity) e faz fallback para DEFAULT_CAPACITY.
        """
        if capacity is None:
            capacity = int(self.capacity or DEFAULT_CAPACITY)
        if capacity <= 0:
            return 0
        total = self.total()
        return round((total / capacity) * 100)

    def to_pie(self):
        """Retorna um dicionário adequado para alimentar o gráfico pie."""
        return {
            'p45': int(self.p45 or 0),
            'p20': int(self.p20 or 0),
            'p13': int(self.p13 or 0),
            'p8': int(self.p8 or 0),
            'p5': int(self.p5 or 0),
            'agua': int(self.agua or 0),
        }
