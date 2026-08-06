from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class ContratacionDirectaAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CONTRATACION_DIRECTA


class ContratacionDirectaJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CONTRATACION_DIRECTA


ContratacionDirectaAgent = ContratacionDirectaAnalistaAgent
