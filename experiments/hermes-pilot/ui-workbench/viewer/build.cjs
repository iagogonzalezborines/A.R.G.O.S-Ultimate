// Uses the pilot's existing reviewed build dependencies; never installs packages.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../../source/node_modules'),esbuild=require(root+'/esbuild');
const version=name=>JSON.parse(fs.readFileSync(root+'/'+name+'/package.json')).version;
const pin=JSON.parse(fs.readFileSync(__dirname+'/pin.json'));for(const name of ['three','esbuild'])if(version(name)!==pin[name])throw Error('Unreviewed '+name+' version');
esbuild.buildSync({entryPoints:[__dirname+'/model.js'],outfile:__dirname+'/model.bundle.js',bundle:true,minify:true,format:'iife',nodePaths:[root],legalComments:'eof'});
console.log(crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/model.bundle.js')).digest('hex'));
