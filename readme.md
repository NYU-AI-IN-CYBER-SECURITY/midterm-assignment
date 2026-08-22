# Midterm Project: LLM Fine-Tuning for Network Intrusion Detection

## Course: AI in Cyber Security
**Midterm Assignment Guide & Submission Instructions**

---

### 1. Project Overview & Context

Previously in this course, you worked with two distinct detectors network security:
1. **Rule-Based Filtering (`if-then-else-Assignment`):** You crafted static boolean logic rules (like `if row['sttl'] > 200...`) to classify connections. You hit a hard performance ceiling because real network data overlaps heavily across feature boundaries, making simple manual cuts insufficient to split normal and malicious traffic cleanly.
2. **Machine Learning Classifiers (`Random-Forest-Assignment`):** You used an ensemble of decision trees to fit tens of thousands of boundaries simultaneously across all features. You wrestled with extreme class imbalances (e.g., rare classes like Worms vs. dominant normal traffic) and optimized macro-averaged metrics (such as macro F1) by implementing preprocessing pipelines (like One-Hot Encoding) to handle categorical feature strings.

#### The LLM Paradigm: Semantic Reasoning
For this midterm project, instead of fitting numeric split-thresholds or hand-written heuristics, you will teach a generative model to perform **semantic reasoning** over network data from a PCAP file. You will format the raw network packets into conversational prompts and fine-tune a small LLM—**Liquid LFM2.5 (350M Parameter Model)**—to analyze packet characteristics and return an explicit security decision (`normal` or `attack`) and its corresponding attack category.

By the end of this project, you will understand how to prepare unstructured data for LLMs, perform supervised fine-tuning, and export self-contained weights for local inference deployment.

---

### 2. Why Liquid AI's LFM2.5 Model?

We are using **Liquid LFM2.5** for this project due to its unique architectural and operational benefits:
* **Compact Hybrid Architecture:** LFM (Liquid Foundation Model) blends short convolution structures with global attention layers. It fits entirely within **1GB to 2.5GB of RAM**, making it extremely lightweight compared to traditional transformer-only architectures.
* **On-Device CPU Performance:** It runs exceptionally fast on modest CPU hardware, allowing you to run, test, and deploy the fine-tuned model locally on any standard computer without needing high-end hardware.
* **Privacy & Local Auditing:** Streaming packet data can be processed entirely locally on-device without exposing sensitive network logs to external cloud APIs or third-party servers.
* **Open Accessibility:** The model features open weights and is fully compatible with lightweight training platforms. Liquid AI was co-founded by **Daniela Rus**, Director of MIT’s Computer Science and Artificial Intelligence Laboratory (CSAIL).

---

### 3. Environment Setup & Unsloth Studio Installation

We will use **Unsloth Studio**, an open-source, no-code/low-code web UI that simplifies downloading, running, fine-tuning, and exporting open-source models. This allows us to focus on the value of data representation and prompt structure, and how LLMs fit into a Cyber Security workflow. 

*(If you prefer command-line/CLI development, you can review [Liquid AI's TRL and Unsloth Integration examples](https://docs.liquid.ai/lfm/fine-tuning/unsloth).)*

#### A. Download Unsloth Studio Desktop
Download the native desktop installer matching your operating system:
*   [Download for macOS](https://unsloth.ai/download/mac)
*   [Download for Windows](https://unsloth.ai/download/windows)
*   [Download for Linux](https://unsloth.ai/download/linux)

Diskspace consumption can get quite high depending on the extent of your model training, be prepared for 80GB-200GB diskspace consumption depending on use. 
Once you install it and open the application, make sure to install any updates!

#### B. Hardware Compatibility
*   **Nvidia Dedicated GPUs:** Works fully out of the box with complete CUDA acceleration (most performant).
*   **Integrated Graphics & Modern CPUs (Intel/AMD):** Integrated chips will be automatically detected and supported.
*   **Apple Silicon (M1/M2/M3/M4):** macOS systems are natively supported out of the box, utilizing Apple's MLX framework for accelerated local inference and training.

#### C. Troubleshooting Guides
If you experience hardware detection, compilation, or driver issues on your device, consult the official installation guides:
*   **Intel CPUs/GPUs:** [Intel Installation Guide](https://unsloth.ai/docs/get-started/install/intel)
*   **AMD CPUs/GPUs:** [AMD Installation Guide](https://unsloth.ai/docs/get-started/install/amd)
*   **Apple Silicon / Metal:** [mlx-tune Guide](https://github.com/ARahim3/mlx-tune)

---

#### Critical Fix: Intel GPU on Windows Triton Error
If you run Unsloth Desktop on **Windows with an Intel GPU** and encounter the following error during launch or training:
> `Failed to import ML libraries: cannot import name 'intel' from 'triton._C.libtriton'`

Follow these exact steps in an **Administrator PowerShell** window to repair and relink Triton:

##### **Step 1: Clean Up Broken Triton Files and Cache**
Remove any broken Triton packages or cached directories that interfere with the Intel XPU compilation. Make sure to replace `<YOURUSERID>` with your actual Windows username:
```powershell
Remove-Item -Recurse -Force "C:\Users\<YOURUSERID>\.unsloth\studio\unsloth_studio\Lib\site-packages\triton" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "C:\Users\<YOURUSERID>\.unsloth\studio\unsloth_studio\Lib\site-packages\triton-*" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$HOME\.triton\cache" -ErrorAction SilentlyContinue
```

##### **Step 2: Force-Reinstall `pytorch-triton-xpu`**
Execute the Python environment's pip within Unsloth Studio's internal directory to reinstall the Intel-specific Triton GPU wheel:
```powershell
& "C:\Users\<YOURUSERID>\.unsloth\studio\unsloth_studio\Scripts\python.exe" -m pip install --force-reinstall --index-url https://download.pytorch.org/whl/xpu pytorch-triton-xpu
```

##### **Step 3: Verify the Installation**
Verify that Triton is linked correctly to the Intel XPU backend using this command. It must output the success message without errors:
```powershell
& "C:\Users\<YOURUSERID>\.unsloth\studio\unsloth_studio\Scripts\python.exe" -c "import triton; from triton._C.libtriton import intel; print('SUCCESS: Intel XPU Triton is linked correctly!')"
```

##### **Step 4: Change Optimizer Settings in Unsloth Studio UI**
Unsloth Studio defaults its advanced hyperparameters to an 8-bit optimizer (`adamw_8bit` or `paged_adamw_8bit`). While natively supported on NVIDIA CUDA, 8-bit bitsandbytes optimizers are **not supported out of the box** by Intel XPU backend architectures.

Before beginning training, make sure to switch your optimizer:
1. In the Unsloth Studio UI, navigate to your model's training configuration screen.
2. Locate the **Optimizer** setting (usually under advanced configurations).
3. Change it from `adamw_8bit` or `paged_adamw_8bit` to the standard **`adamw_torch`** optimizer.

---

#### D. Cloud Fallback: Jupyter Notebook & Google Colab
If your local hardware is not a viable option, a pre-configured **Jupyter Notebook** is provided in this repository under the name `Unsloth_Studio_Colab.ipynb`.
*   Open the notebook in [Google Colab](https://colab.research.google.com/).
*   Use Colab's free cloud T4 GPU compute resources to install and run the Unsloth Studio interface remotely. Note that free Colab tiers face strict file persistence limitations, usage limits, and session timeouts.
*   You **are able** to use Colab and connect to a local runtime (your hardware), if you like. It's extra overhead but some folks prefer the notebook format. However, the 'train' feature will only work if you have a supported GPU available. Unsloth Desktop is better supported, the notebook is designed for Colab Hosted Computing. 
*   *Note: If you run into persistent storage boundaries or experience compute limit timeouts, it is highly recommended to opt into the paid Colab plan to access more advanced hardware (which drastically reduces compute training time) and secure more persistent storage.*

---

### 4. Task 1: Prompt Design & Dataset Structure (`prompter.py`)

To fine-tune your model, network logs must be transformed into structured prompt templates.

As a starting point, use the UNSW-NB15 dataset, along with other network traffic sources that you like. Keep the input data format consistent across your entire dataset!

#### The Dataset: UNSW-NB15

Created by the Australian Centre for Cyber Security at UNSW, mixing real packet captures with synthetic attack traffic from the IXIA PerfectStorm tool.

**Official dataset page:** https://research.unsw.edu.au/projects/unsw-nb15-dataset

**Citation:**
> Moustafa, N., & Slay, J. (2015). UNSW-NB15: a comprehensive data set for network intrusion detection systems. *2015 MilCIS*, IEEE. [DOI](https://doi.org/10.1109/MilCIS.2015.7348942)

We are hosting a subset of UNSW Data for easy download: [Download Link](https://nyu.box.com/s/ahob3ibcszm9i7n9a2jh84sag0dzuuar)
It is recommended that you source your **own** data, not just what we provide. 

Think carefully about how much training data you need. Is 50 data points enough? What about 1,000, 10,000, 100,000, 200,000, or more? Consider how the size and diversity of your dataset may affect the quality of your fine-tuned model.

#### Custom Formatting in `prompter.py`
You have been provided with a template Python script named `prompter.py`. This is where you specify how you plan to prompt your model. Only modify the sections you are given to edit. No more. You may not install any new libraries, dependencies, etc., within the prompter.py file. 

When your model is evaluated, the grading system will present raw network packet details as a dictionary to your prompter.py, which will format it into a set string based on your design and return the prompt for us to feed as a model input to your model. Keep in mind that Liquid LFM2.5 uses a **ChatML-like template format** with `system`, `user`, and `assistant` blocks.

To understand the template details, see [Liquid AI Chat Template Documentation](https://docs.liquid.ai/lfm/key-concepts/chat-template).

Your task in `prompter.py` is to choose what features go into the prompt and how they are displayed. You will be provided with **all labels and features** of the packet, but you must decide:
1. **Which features to include:** Which columns carry high-quality signals? (e.g., `sttl`, `dpkts`, `sload`, `dur`, etc.). Including all 42 features may clutter the context window and slow down training/inference, while too few may cap model performance.
2. **How to represent them:** Should they be formatted as key-value lines, bullet points, structured JSON, or conversational prose?

#### Crucial: Strict JSON Output Format
Your model must be trained to output a **valid JSON object** containing exactly the `label` and `type` keys. If your model deviates from this structure or outputs arbitrary text, it will fail the grading checks.

Your prompt must instruct the model to return outputs in the following exact schema:
```json
{"label": "normal", "type": "Normal"}
```
or
```json
{"label": "attack", "type": "Shellcode"}
```

##### **Allowed Classification Values:**
*   **`label` keys:** Must be exactly `"normal"` or `"attack"`.
*   **`type` keys:** Must be one of the following 10 network categories:
    `Normal`, `Fuzzers`, `Analysis`, `Backdoors`, `DoS`, `Exploits`, `Generic`, `Reconnaissance`, `Shellcode`, `Worms`

Refer to the code comments inside `prompter.py` for more details.

---

### 5. Written Report Requirements

You must include an analytical report as a PDF (`<NYUID>_report.pdf`) or a Markdown file (`<NYUID>_report.md`). Your report must be **between 600 and 2,000 words** and must comprehensively address the following engineering challenges:

#### 1. Dataset Balancing Strategy
Should your training dataset be **balanced (50/50 ratio)** or **left unbalanced (matching real-world traffic)**?
*   Recall that real-world network traffic is heavily skewed—malicious attacks often represent less than 1% of total network logs. How does this affect training?
*   Discuss the concrete trade-offs of training on balanced datasets (e.g., overfitting to synthetic frequencies, misrepresenting actual risk) versus unbalanced datasets.

#### 2. The "All Normal" Majority Blindness
What happens if your model learns a degenerate strategy and returns "Normal" for everything?
*   If a classifier defaults to "Normal", it might achieve 99% accuracy on an unbalanced, real-world wire because attacks are rare.
*   However, its **macro-averaged F1 score** will collapse toward zero, and highly dangerous, low-frequency events (like Worms or Backdoors) will bypass your defense undetected.
*   Detail exactly how you will construct your training splits or adjust class ratios to prevent your LLM from acquiring this majority-class blindness.

#### 3. Prompting vs. Machine Learning Boundaries
*   In the Random Forest assignment, categorical string columns (like `proto`, `service`, `state`) had to be transformed via **one-hot encoding** into 100+ numeric binary columns because decision trees can only evaluate mathematical inequality splits.
*   With your LLM, you are feeding raw strings and natural language logs into a text prompter.
*   What is conceptually different about how an LLM evaluates these categorical features compared to standard machine learning decision boundaries? Explain how semantic embeddings and token attention change how the model captures network patterns.

#### 4. Your Prompting Strategy
*   Explain your chosen prompting strategy, the features you selected, how you structured your template, and why you believe this representation works best.

---

### 6. Task 2: Model Fine-Tuning in Unsloth Studio

Once you have formatted your training data and verified its alignment with your `prompter.py` formatting function, load it into Unsloth Studio to run your training pipeline.

1. **Select the Model:** Choose the **Liquid LFM2.5 (350M Parameter Model)** base model in Unsloth Studio. 
You get to choose between the [LFM2.5-350M model](https://docs.liquid.ai/lfm/models/lfm25-350m) OR  [LFM2.5-Encoder-350M](https://docs.liquid.ai/lfm/models/lfm25-encoder-350m), read up on both and make your choice. 
2. **Upload Dataset:** Feed your formatted data into Unsloth. Open the dataset configuration and make sure to map the target labels yourself.
3. **Choose Adaptation Method:** Select your adapter training configurations:
   * **LoRA (Low-Rank Adaptation)**
   * **QLoRA (Quantized Low-Rank Adaptation)**
   * **Full-Model Weights Training**
   * *Note: Since this 350M parameter model is extremely lightweight, quantization (such as 4-bit loading) is not required for memory conservation during training, allowing you to train with higher fidelity weights. Most students select **full-model weights training**.*
4. **Export as GGUF:** Once training completes, use Unsloth's export engine to export your model into a unified **GGUF format** (`.gguf`). Make sure that your trained weights are **fully merged** into the base model weights during the GGUF export. Not need to apply quantization here FP16 is okay (the model is quite small). 

---

### 📤 Submission Requirements

You must upload the following three deliverables to the course submission portal:

1. **`prompter.py`:** Your prompt engineering script containing your dataset formatting logic.
2. **`<NYUID>.gguf`:** Your fine-tuned, merged GGUF model exported from Unsloth Studio.
3. **`<NYUID>_report.pdf`** (or **`<NYUID>_report.md`**): Your analytical report addressing the four conceptual questions on dataset balancing, majority blindness, and semantic boundaries (600 to 1,200 words).

*Note: Replace `<NYUID>` with your actual NYU NetID in the filenames.*

#### Grading Criteria
* For the report, there is no hard numeric rubric for performance. You are graded on your **demonstrated effort** and the **correctness/depth of thought** in your analytical report answers. It is Pass/Fail.
* For the performance of your model, you will receive a score similar to the previous assignments.
  
#### Important! How Model Benchmarking Works

* Once you upload your model to the portal, it will be placed in a queue for benchmarking. Benchmarking is performed on **Torch, NYU Tandon's supercomputer**, and is **not instantaneous**.
* Benchmarking runs on a fixed schedule: **Monday, Wednesday, and Friday**. Uploads are accepted until **8:00 PM ET** on the day of benchmarking. Submissions received by the deadline will be placed in the queue.
* You will receive your benchmarking score **the following day**. You can then choose to:

  * **Keep your score** by uploading the provided token to Gradescope, or
  * **Submit a revised version** for another benchmarking attempt.
* You are permitted a maximum of **5 benchmarking attempts**. Each attempt will generate a unique use token.
* You can earn **extra credit for minimizing the number of submissions**. You start with **10 points of extra credit**, and each submission after the first reduces the available extra credit by **4 points**.
* **Every submission counts**, regardless of whether you ultimately use that submission's score for your final grade. We strongly recommend testing your model locally and making sure it is performing as expected before submitting it for benchmarking. You cannot mix and match parts of a submission. Each submission must include all files (including the report). 

| Number of Submissions |  Extra Credit |
| --------------------: | ------------: |
|                     1 | **10 points** |
|                     2 |  **6 points** |
|                     3 |  **2 points** |
|                    4+ |  **0 points** |

**Important:** If you use all 5 submissions, you forfeit the full **12 points of extra credit available on the midterm project**.


Good luck! Let's see how well an LLM can defend the network.
