import logging
import sys
import json
from modules.pipeline.runner import PipelineRunner

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

fasta = "dummy_test_real.fna"

runner = PipelineRunner()
res = runner.run(
    run_id="decoy_test",
    fasta_path=fasta,
    fasta_filename="dummy_test_real.fna",
    evalue=1e-5,
    program="blastx",
    stage_callback=lambda x: print(f"Stage: {x}")
)
print(f"Total Hits: {len(res.hits)}")

import pprint
for hit in res.hits:
    print("\n--- Hit Result ---")
    pprint.pprint(hit)
