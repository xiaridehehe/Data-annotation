import urllib.request
for name,file in [('libjpeg-turbo-8bit','libjpegturbowasm_decode'),('charls','charlswasm_decode'),('openjpeg','openjpegwasm_decode'),('openjph','openjphjs')]:
 url=f'http://127.0.0.1:5180/node_modules/@cornerstonejs/codec-{name}/dist/{file}.js'
 source=urllib.request.urlopen(url).read().decode()
 assert 'export default module.exports' in source, name
 print(name, 'dev module export OK')
