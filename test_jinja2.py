import sys
sys.path.insert(0, '/root/photo-album-generator')
from jinja2 import Environment

env = Environment()
page = {'style': 'template_structured', 'data': {'template_id': 'T3', 'template_name': 'test', 'zones': []}}
template = env.from_string('{{ page.data.template_id }}')
result = template.render(page=page)
print(f'Jinja2 version: {__import__("jinja2").__version__}')
print(f'Result: {result}')

# Also test set
template2 = env.from_string('{% set tmpl_id = page.data.template_id or "T1" %}{{ tmpl_id }}')
result2 = template2.render(page=page)
print(f'Set result: {result2}')
