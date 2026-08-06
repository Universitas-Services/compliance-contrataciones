from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class ConcursoCerradoAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CONCURSO_CERRADO


class ConcursoCerradoJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CONCURSO_CERRADO


ConcursoCerradoAgent = ConcursoCerradoAnalistaAgent
