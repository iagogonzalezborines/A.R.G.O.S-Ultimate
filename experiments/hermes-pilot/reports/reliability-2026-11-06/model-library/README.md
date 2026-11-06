# Local STL/OBJ catalogue prototype

This prototype runs locally and uses only Python's standard library. It indexes
`.stl` and `.obj` files recursively; it does not modify model files, contact
printers, run slicers, or make network requests.

## API

```python
from catalogue import ModelLibrary

library = ModelLibrary("catalogue.sqlite")
library.index("./models")
library.tag("/absolute/path/to/model.stl", ["prototype", "bracket"])
library.note("/absolute/path/to/model.stl", "Print with supports")
results = library.search("supports")
library.close()
```

`index(folder)` returns the number of supported files discovered. Re-indexing
updates indexed file metadata without creating duplicate records. `tag()`
replaces a model's tag list; `note()` appends a note. Both require an indexed
absolute path (relative inputs are resolved to absolute paths). `search(query)`
returns dictionaries containing `path`, `name`, `extension`, `size`, `sha256`,
`tags`, and `notes`, matching the query case-insensitively against the filename,
tags, or notes. Data is stored in the SQLite database at `db_path`.

## CLI

The command-line interface uses the same local SQLite database and requires no
packages beyond Python's standard library. Put `--db` before the subcommand:

```sh
python catalogue.py --db RUTA_DB index CARPETA
python catalogue.py --db RUTA_DB tag RUTA_ABSOLUTA ETIQUETAS...
python catalogue.py --db RUTA_DB note RUTA_ABSOLUTA TEXTO
python catalogue.py --db RUTA_DB search CONSULTA
```

`index` scans a folder recursively and prints the number of STL/OBJ files
indexed. `tag` replaces the indexed model's tags (provide one or more). `note`
appends the supplied note text. Quote paths or multiword values for your shell,
for example:

```sh
python catalogue.py --db ./catalogue.sqlite index ./models
python catalogue.py --db ./catalogue.sqlite tag "/absolute/path/Cube.stl" prototype bracket
python catalogue.py --db ./catalogue.sqlite note "/absolute/path/Cube.stl" "print with supports"
python catalogue.py --db ./catalogue.sqlite search supports
```

`search` writes a JSON array to stdout; each result includes its tags and notes.
Metadata commands require that the model has already been indexed. The CLI
operates only on local files and the selected database.

## Verification

Run the standard-library test suite from this directory:

```sh
python3 -m unittest -v
```
