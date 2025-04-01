"""
Canary Deployment Monitoring Script

This script monitors a canary deployment by comparing metrics between
canary and production environments to detect anomalies and determine
if the canary deployment is healthy.
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('canary_monitor.log')
    ]
)
logger = logging.getLogger('canary_monitor')


class CanaryMonitor:
    """Monitors canary deployments by comparing metrics with production."""
    
    def __init__(
        self,
        canary_url: str,
        production_url: str,
        metrics_endpoint: str = '/metrics',
        health_endpoint: str = '/health',
        api_key: Optional[str] = None,
        threshold_multiplier: float = 1.5,
        error_threshold: float = 0.05
    ):
        """Initialize the canary monitor.
        
        Args:
            canary_url: Base URL of the canary deployment
            production_url: Base URL of the production deployment
            metrics_endpoint: Endpoint for metrics API
            health_endpoint: Endpoint for health check API
            api_key: Optional API key for authentication
            threshold_multiplier: Multiplier for thresholds (e.g., 1.5 means 50% worse is an alert)
            error_threshold: Absolute threshold for error rate (e.g., 0.05 means 5% errors is an alert)
        """
        self.canary_url = canary_url.rstrip('/')
        self.production_url = production_url.rstrip('/')
        self.metrics_endpoint = metrics_endpoint
        self.health_endpoint = health_endpoint
        self.api_key = api_key
        self.threshold_multiplier = threshold_multiplier
        self.error_threshold = error_threshold
        self.headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
        self.results = []
        self.start_time = datetime.now()
    
    def check_health(self) -> Tuple[bool, bool]:
        """Check if both environments are healthy.
        
        Returns:
            Tuple of (canary_healthy, production_healthy)
        """
        try:
            canary_health = requests.get(
                f"{self.canary_url}{self.health_endpoint}",
                headers=self.headers,
                timeout=10
            )
            canary_healthy = canary_health.status_code == 200
        except Exception as e:
            logger.error(f"Error checking canary health: {e}")
            canary_healthy = False
        
        try:
            production_health = requests.get(
                f"{self.production_url}{self.health_endpoint}",
                headers=self.headers,
                timeout=10
            )
            production_healthy = production_health.status_code == 200
        except Exception as e:
            logger.error(f"Error checking production health: {e}")
            production_healthy = False
        
        logger.info(f"Health check: Canary: {'✅' if canary_healthy else '❌'}, "
                   f"Production: {'✅' if production_healthy else '❌'}")
        
        return canary_healthy, production_healthy
    
    def get_metrics(self, environment: str) -> Dict[str, Any]:
        """Get metrics from the specified environment.
        
        Args:
            environment: Either 'canary' or 'production'
        
        Returns:
            Dictionary of metrics or empty dict if failed
        """
        url = self.canary_url if environment == 'canary' else self.production_url
        
        try:
            response = requests.get(
                f"{url}{self.metrics_endpoint}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get metrics from {environment}: {response.status_code}")
                return {}
        except Exception as e:
            logger.error(f"Error getting metrics from {environment}: {e}")
            return {}
    
    def compare_metrics(self) -> Dict[str, Any]:
        """Compare metrics between canary and production.
        
        Returns:
            Dictionary with comparison results
        """
        canary_metrics = self.get_metrics('canary')
        production_metrics = self.get_metrics('production')
        
        if not canary_metrics or not production_metrics:
            return {
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'message': 'Failed to retrieve metrics from one or both environments',
                'canary_metrics_available': bool(canary_metrics),
                'production_metrics_available': bool(production_metrics)
            }
        
        # Extract key metrics for comparison
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy',
            'anomalies': [],
            'metrics': {}
        }
        
        # Compare error rates
        canary_error_rate = canary_metrics.get('error_rate', 0)
        production_error_rate = production_metrics.get('error_rate', 0)
        
        comparison['metrics']['error_rate'] = {
            'canary': canary_error_rate,
            'production': production_error_rate,
            'difference': canary_error_rate - production_error_rate,
            'percent_change': (
                ((canary_error_rate - production_error_rate) / max(production_error_rate, 0.001)) * 100
            )
        }
        
        if canary_error_rate > self.error_threshold:
            comparison['anomalies'].append({
                'metric': 'error_rate',
                'message': f"Canary error rate ({canary_error_rate:.2%}) exceeds threshold ({self.error_threshold:.2%})"
            })
            comparison['status'] = 'degraded'
        
        # Compare response times
        canary_response_time = canary_metrics.get('avg_response_time_ms', 0)
        production_response_time = production_metrics.get('avg_response_time_ms', 0)
        
        comparison['metrics']['response_time'] = {
            'canary': canary_response_time,
            'production': production_response_time,
            'difference': canary_response_time - production_response_time,
            'percent_change': (
                ((canary_response_time - production_response_time) / max(production_response_time, 1)) * 100
            )
        }
        
        if canary_response_time > production_response_time * self.threshold_multiplier:
            comparison['anomalies'].append({
                'metric': 'response_time',
                'message': (
                    f"Canary response time ({canary_response_time:.2f}ms) is "
                    f"{comparison['metrics']['response_time']['percent_change']:.2f}% higher than "
                    f"production ({production_response_time:.2f}ms)"
                )
            })
            comparison['status'] = 'degraded'
        
        # Compare memory usage
        canary_memory = canary_metrics.get('memory_usage_mb', 0)
        production_memory = production_metrics.get('memory_usage_mb', 0)
        
        comparison['metrics']['memory_usage'] = {
            'canary': canary_memory,
            'production': production_memory,
            'difference': canary_memory - production_memory,
            'percent_change': (
                ((canary_memory - production_memory) / max(production_memory, 1)) * 100
            )
        }
        
        if canary_memory > production_memory * self.threshold_multiplier:
            comparison['anomalies'].append({
                'metric': 'memory_usage',
                'message': (
                    f"Canary memory usage ({canary_memory:.2f}MB) is "
                    f"{comparison['metrics']['memory_usage']['percent_change']:.2f}% higher than "
                    f"production ({production_memory:.2f}MB)"
                )
            })
            comparison['status'] = 'degraded'
        
        # Compare CPU usage
        canary_cpu = canary_metrics.get('cpu_usage_percent', 0)
        production_cpu = production_metrics.get('cpu_usage_percent', 0)
        
        comparison['metrics']['cpu_usage'] = {
            'canary': canary_cpu,
            'production': production_cpu,
            'difference': canary_cpu - production_cpu,
            'percent_change': (
                ((canary_cpu - production_cpu) / max(production_cpu, 1)) * 100
            )
        }
        
        if canary_cpu > production_cpu * self.threshold_multiplier:
            comparison['anomalies'].append({
                'metric': 'cpu_usage',
                'message': (
                    f"Canary CPU usage ({canary_cpu:.2f}%) is "
                    f"{comparison['metrics']['cpu_usage']['percent_change']:.2f}% higher than "
                    f"production ({production_cpu:.2f}%)"
                )
            })
            comparison['status'] = 'degraded'
        
        return comparison
    
    def monitor(self, duration_minutes: int, interval_seconds: int) -> Dict[str, Any]:
        """Monitor canary deployment for the specified duration.
        
        Args:
            duration_minutes: Duration to monitor in minutes
            interval_seconds: Interval between checks in seconds
        
        Returns:
            Dictionary with monitoring results
        """
        logger.info(f"Starting canary monitoring for {duration_minutes} minutes "
                   f"(checking every {interval_seconds} seconds)")
        
        end_time = self.start_time + timedelta(minutes=duration_minutes)
        
        while datetime.now() < end_time:
            # Check health first
            canary_healthy, production_healthy = self.check_health()
            
            if not canary_healthy:
                self.results.append({
                    'timestamp': datetime.now().isoformat(),
                    'status': 'critical',
                    'message': 'Canary health check failed'
                })
                logger.error("Canary health check failed")
            elif not production_healthy:
                logger.warning("Production health check failed, skipping this check")
                time.sleep(interval_seconds)
                continue
            else:
                # Compare metrics
                comparison = self.compare_metrics()
                self.results.append(comparison)
                
                if comparison['status'] != 'healthy':
                    logger.warning(f"Detected anomalies: {len(comparison['anomalies'])}")
                    for anomaly in comparison['anomalies']:
                        logger.warning(f"  - {anomaly['message']}")
                else:
                    logger.info("Canary metrics within acceptable thresholds")
            
            # Wait for next check
            time.sleep(interval_seconds)
        
        return self.get_final_result()
    
    def get_final_result(self) -> Dict[str, Any]:
        """Get the final monitoring result.
        
        Returns:
            Dictionary with final monitoring results
        """
        # Count statuses
        status_counts = {'healthy': 0, 'degraded': 0, 'critical': 0, 'error': 0}
        anomaly_counts = {}
        
        for result in self.results:
            status = result.get('status', 'error')
            status_counts[status] = status_counts.get(status, 0) + 1
            
            for anomaly in result.get('anomalies', []):
                metric = anomaly.get('metric')
                if metric:
                    anomaly_counts[metric] = anomaly_counts.get(metric, 0) + 1
        
        # Calculate percentages
        total_checks = len(self.results)
        healthy_percent = (status_counts.get('healthy', 0) / max(total_checks, 1)) * 100
        
        # Determine overall status
        if status_counts.get('critical', 0) > 0:
            overall_status = 'failed'
            recommendation = 'rollback'
        elif status_counts.get('degraded', 0) > total_checks * 0.3:  # More than 30% degraded
            overall_status = 'unstable'
            recommendation = 'investigate'
        else:
            overall_status = 'passed'
            recommendation = 'promote'
        
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'duration_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
            'total_checks': total_checks,
            'status_counts': status_counts,
            'healthy_percent': healthy_percent,
            'anomaly_counts': anomaly_counts,
            'overall_status': overall_status,
            'recommendation': recommendation,
            'detailed_results': self.results
        }
    
    def save_results(self, output_file: str) -> None:
        """Save monitoring results to a file.
        
        Args:
            output_file: Path to the output file
        """
        with open(output_file, 'w') as f:
            json.dump(self.get_final_result(), f, indent=2)
        
        logger.info(f"Results saved to {output_file}")
    
    def print_summary(self) -> None:
        """Print a summary of monitoring results."""
        final_result = self.get_final_result()
        
        print("\n" + "=" * 60)
        print("CANARY DEPLOYMENT MONITORING SUMMARY")
        print("=" * 60)
        print(f"Duration: {final_result['duration_minutes']:.2f} minutes")
        print(f"Total Checks: {final_result['total_checks']}")
        print(f"Healthy Checks: {final_result['status_counts'].get('healthy', 0)} "
              f"({final_result['healthy_percent']:.2f}%)")
        print(f"Degraded Checks: {final_result['status_counts'].get('degraded', 0)}")
        print(f"Critical Checks: {final_result['status_counts'].get('critical', 0)}")
        print(f"Error Checks: {final_result['status_counts'].get('error', 0)}")
        print("-" * 60)
        
        if final_result['anomaly_counts']:
            print("Anomalies Detected:")
            for metric, count in final_result['anomaly_counts'].items():
                print(f"  - {metric}: {count} occurrences")
        else:
            print("No anomalies detected")
        
        print("-" * 60)
        print(f"Overall Status: {final_result['overall_status'].upper()}")
        print(f"Recommendation: {final_result['recommendation'].upper()}")
        print("=" * 60)


def main():
    """Main entry point for canary monitoring."""
    parser = argparse.ArgumentParser(description='Monitor canary deployment')
    parser.add_argument('--canary-url', required=True,
                      help='Base URL of the canary deployment')
    parser.add_argument('--production-url', required=True,
                      help='Base URL of the production deployment')
    parser.add_argument('--metrics-endpoint', default='/metrics',
                      help='Endpoint for metrics API')
    parser.add_argument('--health-endpoint', default='/health',
                      help='Endpoint for health check API')
    parser.add_argument('--api-key',
                      help='API key for authentication')
    parser.add_argument('--duration', type=int, default=15,
                      help='Duration to monitor in minutes')
    parser.add_argument('--interval', type=int, default=30,
                      help='Interval between checks in seconds')
    parser.add_argument('--threshold', type=float, default=1.5,
                      help='Threshold multiplier for alerts')
    parser.add_argument('--error-threshold', type=float, default=0.05,
                      help='Absolute threshold for error rate')
    parser.add_argument('--output', default='canary_results.json',
                      help='File to save results to')
    args = parser.parse_args()
    
    # Create monitor
    monitor = CanaryMonitor(
        canary_url=args.canary_url,
        production_url=args.production_url,
        metrics_endpoint=args.metrics_endpoint,
        health_endpoint=args.health_endpoint,
        api_key=args.api_key,
        threshold_multiplier=args.threshold,
        error_threshold=args.error_threshold
    )
    
    # Run monitoring
    monitor.monitor(args.duration, args.interval)
    
    # Save and print results
    monitor.save_results(args.output)
    monitor.print_summary()
    
    # Exit with appropriate code based on recommendation
    final_result = monitor.get_final_result()
    if final_result['recommendation'] == 'rollback':
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
