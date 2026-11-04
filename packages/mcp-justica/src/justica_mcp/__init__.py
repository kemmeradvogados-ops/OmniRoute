"""Camada padronizadora de acesso processual da Kemmer Advogados."""
# NAO DIGITE UM NUMERO AQUI. Ate 04/11/2026 este literal dizia "0.1.0"
# enquanto o manifesto e o pyproject diziam 0.9.9, e ninguem percebeu por
# meses. A versao que vale e a do manifesto, que acompanha cada entrega;
# `versao_instalada` a le e nunca levanta erro.
from .core.versao import versao_instalada as _versao_instalada

__version__ = _versao_instalada()
