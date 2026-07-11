#!/usr/bin/env python3
"""
generate_graphs.py
===================
Assignment 6 - GUI-Based Multi-Client Chat Application Using TCP

Reads the performance and chat-history CSV files produced during testing
and generates three graphs required by the assignment:

    graphs/clients_vs_delay.png            Average message delay vs. number
                                            of concurrent clients.
    graphs/clients_vs_throughput.png       Server throughput (messages/sec)
                                            vs. number of concurrent clients.
    graphs/message_type_distribution.png   Pie chart of broadcast vs. private
                                            message volume observed across
                                            the test runs.

Usage
-----
    python generate_graphs.py

Requires: pandas, matplotlib (see requirements.txt)
"""

import os
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless-safe backend, no display required
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERFORMANCE_CSV = os.path.join(BASE_DIR, "performance_results.csv")
CHAT_HISTORY_CSV = os.path.join(BASE_DIR, "chat_history.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "graphs")

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#f7f9fb",
    "axes.edgecolor": "#444444",
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "font.size": 11,
})


def load_performance_data(path):
    if not os.path.exists(path):
        sys.exit(f"ERROR: performance results file not found: {path}")
    df = pd.read_csv(path)
    required_cols = {"num_clients", "avg_delay_ms", "throughput_msgs_per_sec",
                      "broadcast_count", "private_count"}
    missing = required_cols - set(df.columns)
    if missing:
        sys.exit(f"ERROR: performance_results.csv is missing columns: {missing}")
    return df.sort_values("num_clients")


def plot_clients_vs_delay(df, output_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(df["num_clients"], df["avg_delay_ms"], marker="o", linewidth=2,
            color="#d64545", markersize=7, label="Average delay")
    ax.set_title("Average Message Delay vs. Number of Connected Clients", fontsize=13, fontweight="bold")
    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Average Delay (ms)")
    ax.set_xticks(df["num_clients"])
    for x, y in zip(df["num_clients"], df["avg_delay_ms"]):
        ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_clients_vs_throughput(df, output_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(df["num_clients"], df["throughput_msgs_per_sec"], color="#3d7eff", width=1.2,
           edgecolor="#1e2530")
    ax.set_title("Server Throughput vs. Number of Connected Clients", fontsize=13, fontweight="bold")
    ax.set_xlabel("Number of Concurrent Clients")
    ax.set_ylabel("Throughput (messages/second)")
    ax.set_xticks(df["num_clients"])
    for x, y in zip(df["num_clients"], df["throughput_msgs_per_sec"]):
        ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_message_type_distribution(df, history_path, output_path):
    total_broadcast = int(df["broadcast_count"].sum())
    total_private = int(df["private_count"].sum())

    # Cross-check against chat_history.csv if it exists, for transparency.
    if os.path.exists(history_path):
        hist = pd.read_csv(history_path)
        hist_broadcast = int((hist["message_type"] == "BROADCAST").sum())
        hist_private = int((hist["message_type"] == "PRIVATE").sum())
        print(f"(chat_history.csv contains {hist_broadcast} broadcast and "
              f"{hist_private} private message rows for cross-reference)")

    labels = ["Broadcast Messages", "Private Messages"]
    sizes = [total_broadcast, total_private]
    colors = ["#3d7eff", "#c792ea"]

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct=lambda p: f"{p:.1f}%\n({int(round(p * sum(sizes) / 100))})",
        startangle=90, textprops={"fontsize": 10}
    )
    ax.set_title("Message Type Distribution (All Test Runs)", fontsize=13, fontweight="bold")
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {output_path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = load_performance_data(PERFORMANCE_CSV)

    plot_clients_vs_delay(df, os.path.join(OUTPUT_DIR, "clients_vs_delay.png"))
    plot_clients_vs_throughput(df, os.path.join(OUTPUT_DIR, "clients_vs_throughput.png"))
    plot_message_type_distribution(df, CHAT_HISTORY_CSV, os.path.join(OUTPUT_DIR, "message_type_distribution.png"))

    print("\nAll graphs generated successfully in the 'graphs/' directory.")


if __name__ == "__main__":
    main()
