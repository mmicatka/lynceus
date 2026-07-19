// modules/local/generate_docking_boxes/main.nf


process GENERATE_DOCKING_BOXES {
    label 'process_single'

    container "lynceus/generate-docking-boxes:0.1.0"

    input:
    path sites_json

    output:
    path "boxes/*.boxes.json", emit: boxes
    path "versions.yml", emit: versions

    script:
    """
  python3 -m generate_docking_boxes.generate_docking_boxes \\
      --sites-json '${sites_json}' \\
      --output boxes.json'

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      python: \$(python3 --version | sed 's/Python //g')
  END_VERSIONS
  """

    stub:
    """
  mkdir -p boxes
  touch boxes/stub.boxes.json

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      python: \$(python3 --version | sed 's/Python //g')
  END_VERSIONS
  """
}
