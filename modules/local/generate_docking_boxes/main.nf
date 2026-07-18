// modules/local/generate_docking_boxes/main.nf


process GENERATE_DOCKING_BOXES {
  tag "${conformational_state_id}"
  label 'process_single'

  container "lynceus/generate-docking-boxes:0.1.0"

  input:
  tuple val(conformational_state_id), path(sites_json)

  output:
  tuple val(conformational_state_id), path("*.boxes.json"), emit: boxes
  path "versions.yml", emit: versions

  script:
  """
  python3 -m generate_docking_boxes.generate_docking_boxes \\
      --sites-json '${sites_json}' \\
      --output '${conformational_state_id}.boxes.json'

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      python: \$(python3 --version | sed 's/Python //g')
  END_VERSIONS
  """

  stub:
  """
  touch ${conformational_state_id}.boxes.json

  cat <<-END_VERSIONS > versions.yml
  "${task.process}":
      python: \$(python3 --version | sed 's/Python //g')
  END_VERSIONS
  """
}
