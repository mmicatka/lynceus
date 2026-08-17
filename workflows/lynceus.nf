// workflows/lynceus.nf

include { CANDIDATE } from '../subworkflows/local/candidate'

workflow LYNCEUS {
  def use_local = params.candidates_local_path as boolean

  ch_uri_list = use_local ? [] : file(params.uri_list, checkIfExists: true)
  ch_local_path = use_local ? file(params.candidates_local_path, checkIfExists: true) : []
  filter_config = file(params.filter.config, checkIfExists: true)

  CANDIDATE(ch_uri_list, ch_local_path, filter_config, params.filter.batch_size)

  _ch_collated_versions = channel.topic('versions')
    .distinct()
    .map { process, tool, version ->
      [process[process.lastIndexOf(':') + 1..-1], "    ${tool}: ${version}"]
    }
    .groupTuple(by: 0)
    .map { process, tool_versions ->
      "${process}:\n${tool_versions.unique().sort().join('\n')}"
    }
    .collectFile(
      storeDir: "${params.outdir}/pipeline_info",
      name: 'software_versions.yml',
      sort: true,
      newLine: true,
    )
}
