# 🛡️ Ultra FSN Parser & CSV Generator

An intelligent automation tool built with **Streamlit** to parse Flipkart/E-commerce FSNs and values from various messy text formats and convert them into structured CSVs for bulk uploads.

## 🚀 Features

- **Smart Parsing**: Automatically pairs 16-character FSNs with their corresponding values, even if they are side-by-side or in stacked lists.
- **Multiple Modes**:
  - **Percentage**: Uses `UT_disc_percent_cat`, `UT_disc_percent`, and `LT_disc_percent`.
  - **ASP (Average Selling Price)**: Uses `custom_14`, `UT_absolute`, and `LT_absolute`.
  - **P0 Mode**: Uses `mrp_disc_percent`, `UT_disc_percent`, and `LT_disc_percent`.
- **Advanced Math Logic**: Supports natural language instructions like `LT - plus 10` or `LT 44` to override specific keys.
- **Instant Export**: Preview the data table and download a ready-to-use CSV file.

## 🛠️ Installation & Local Setup

If you want to run this app locally:

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/fsn-smart-parser.git](https://github.com/YOUR_USERNAME/fsn-smart-parser.git)
   cd fsn-smart-parser
