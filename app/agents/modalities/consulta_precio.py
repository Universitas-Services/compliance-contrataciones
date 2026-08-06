from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class ConsultaPrecioAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CONSULTA_PRECIO


class ConsultaPrecioJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CONSULTA_PRECIO


ConsultaPrecioAgent = ConsultaPrecioAnalistaAgent
