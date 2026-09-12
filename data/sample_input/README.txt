Place small FASTA samples in this folder for integration tests and manual checks.
For example: .fasta, .fa, .fna files downloaded from NCBI.

Current sample:
- dummy_data.fasta is tuned for blastx with the default project thresholds
	(identity >= 40, coverage >= 70, e-value <= 1e-5) and produces
	2 filtered candidate hits in local validation.
