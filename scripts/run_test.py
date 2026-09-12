import logging
import sys
from modules.pipeline.runner import PipelineRunner

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

fasta = r"C:\Users\USER\Desktop\ncbi_dataset\ncbi_dataset\data\GCF_000409715.1\GCF_000409715.1_Klebsiella_pneumoniae_ATCC_25955_Genome_sequencing_genomic.fna"

runner = PipelineRunner()
res = runner.run(
    run_id="test",
    fasta_path=fasta,
    fasta_filename="test.fna",
    evalue=1e-5,
    program="blastx",
    stage_callback=lambda x: print(f"Stage: {x}")
)
print(f"Total Hits: {len(res.hits)}")
